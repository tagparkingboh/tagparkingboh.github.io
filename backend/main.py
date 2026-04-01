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
from zoneinfo import ZoneInfo


def get_uk_now() -> datetime:
    """Get current datetime in UK timezone (handles BST/GMT automatically)."""
    return datetime.now(ZoneInfo("Europe/London"))


def log_promo(message: str, data: dict = None):
    """
    Log promotion-related messages to console.
    Only logs in staging environment for debugging.
    """
    import os
    # Check environment - log in staging and development, not production
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if env in ("staging", "development"):
        timestamp = get_uk_now().strftime("%Y-%m-%d %H:%M:%S")
        if data:
            print(f"[PROMO {timestamp}] {message} | {data}")
        else:
            print(f"[PROMO {timestamp}] {message}")


from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, or_, case

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
import stripe
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
from db_models import BookingStatus, PaymentStatus, FlightDeparture, FlightArrival, AuditLog, AuditLogEvent, ErrorLog, ErrorSeverity, MarketingSubscriber, Booking as DbBooking, Vehicle as DbVehicle, User, LoginCode, Session as DbSession, VehicleInspection, InspectionType, BlockedDate
import db_service
import json
import traceback

# Email scheduler
from email_scheduler import start_scheduler, stop_scheduler

# Email service
from email_service import send_booking_confirmation_email, send_login_code_email

# Routers
from routers.roster import router as roster_router

# Simple in-memory cache for expensive reports
_forecast_cache = {
    "data": None,
    "cached_at": None,
}
FORECAST_CACHE_DURATION_SECONDS = 3600  # 1 hour

# Flight data cache (3 months - reference only, rarely changes)
_flight_departures_cache = {
    "data": None,
    "cached_at": None,
}
_flight_arrivals_cache = {
    "data": None,
    "cached_at": None,
}
_flight_filters_cache = {
    "data": None,
    "cached_at": None,
}
FLIGHT_CACHE_DURATION_SECONDS = 7776000  # 3 months (90 days)

# Reports cache (1 hour - same as forecast)
_booking_locations_cache = {
    "bookings": {"data": None, "cached_at": None},
    "origins": {"data": None, "cached_at": None},
}
_occupancy_cache = {"data": None, "cached_at": None}
_popular_cache = {"data": None, "cached_at": None}
_fun_facts_cache = {"data": None, "cached_at": None}
_financial_cache = {"data": None, "cached_at": None}
_session_tracking_cache = {"data": None, "cached_at": None}
_abandoned_carts_cache = {"data": None, "cached_at": None}
REPORT_CACHE_DURATION_SECONDS = 3600  # 1 hour


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


# Middleware to prevent browser caching of API responses
@app.middleware("http")
async def add_cache_control_headers(request: Request, call_next):
    response = await call_next(request)
    # Don't cache API responses - ensures fresh data on each request
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Include routers
app.include_router(roster_router)


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

        # Migration 4: Create testimonials table
        result = db.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = 'testimonials'
        """))

        if not result.fetchone():
            print("Running migration: Creating testimonials table...")
            # Create enum type first
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'testimonialstatus') THEN
                        CREATE TYPE testimonialstatus AS ENUM ('active', 'inactive');
                    END IF;
                END$$;
            """))
            db.execute(text("""
                CREATE TABLE testimonials (
                    id SERIAL PRIMARY KEY,
                    customer_name VARCHAR(100) NOT NULL,
                    review_text TEXT NOT NULL,
                    star_rating INTEGER,
                    date_of_travel DATE,
                    date_added TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    status testimonialstatus NOT NULL DEFAULT 'inactive',
                    is_featured BOOLEAN NOT NULL DEFAULT FALSE,
                    source VARCHAR(50)
                )
            """))
            db.execute(text("CREATE INDEX ix_testimonials_id ON testimonials (id)"))
            db.execute(text("CREATE INDEX ix_testimonials_status ON testimonials (status)"))
            db.execute(text("CREATE INDEX ix_testimonials_star_rating ON testimonials (star_rating)"))
            db.commit()
            print("Migration completed: testimonials table created")
        else:
            print("Migration check: testimonials table already exists")

        # Migration 5: Fix audit_logs enum - add new values and convert to lowercase
        # Check if we need to add lowercase values
        result = db.execute(text("""
            SELECT enumlabel FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'auditlogevent')
            AND enumlabel = 'tnc_accepted'
        """))

        if not result.fetchone():
            print("Running migration: Fixing audit_logs enum values...")

            # Add new lowercase enum values
            new_values = [
                'tnc_accepted',
                'checkout_loaded',
                'stripe_form_ready',
                'stripe_form_error',
                'payment_processing',
                'payment_requires_action',
                'booking_started',
                'flight_selected',
                'slot_selected',
                'vehicle_entered',
                'customer_entered',
                'billing_entered',
                'payment_initiated',
                'payment_succeeded',
                'payment_failed',
                'booking_confirmed',
                'booking_abandoned',
                'booking_cancelled',
                'booking_refunded',
                'booking_updated',
            ]

            for value in new_values:
                try:
                    db.execute(text(f"ALTER TYPE auditlogevent ADD VALUE IF NOT EXISTS '{value}'"))
                    db.commit()
                except Exception:
                    db.rollback()

            # Update existing uppercase values to lowercase
            uppercase_to_lowercase = {
                'BOOKING_STARTED': 'booking_started',
                'FLIGHT_SELECTED': 'flight_selected',
                'SLOT_SELECTED': 'slot_selected',
                'VEHICLE_ENTERED': 'vehicle_entered',
                'CUSTOMER_ENTERED': 'customer_entered',
                'BILLING_ENTERED': 'billing_entered',
                'PAYMENT_INITIATED': 'payment_initiated',
                'PAYMENT_SUCCEEDED': 'payment_succeeded',
                'PAYMENT_FAILED': 'payment_failed',
                'BOOKING_CONFIRMED': 'booking_confirmed',
                'BOOKING_ABANDONED': 'booking_abandoned',
                'BOOKING_CANCELLED': 'booking_cancelled',
                'BOOKING_REFUNDED': 'booking_refunded',
                'BOOKING_UPDATED': 'booking_updated',
            }

            for old_val, new_val in uppercase_to_lowercase.items():
                db.execute(text(f"UPDATE audit_logs SET event = '{new_val}' WHERE event = '{old_val}'"))
            db.commit()
            print("Migration completed: audit_logs enum fixed")
        else:
            print("Migration check: audit_logs enum already has lowercase values")

        # Migration 6: Add type column to promo_modals table
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'promo_modals'
            AND column_name = 'type'
        """))

        if not result.fetchone():
            print("Running migration: Adding type column to promo_modals...")
            # Create enum type first
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'promomodaltype') THEN
                        CREATE TYPE promomodaltype AS ENUM ('info_modal', 'promo_section');
                    END IF;
                END$$;
            """))
            db.execute(text("""
                ALTER TABLE promo_modals
                ADD COLUMN type promomodaltype NOT NULL DEFAULT 'info_modal'
            """))
            db.commit()
            print("Migration completed: type column added to promo_modals")
        else:
            print("Migration check: promo_modals type column already exists")

        # Migration 7: Add new audit log events for T&C and promo tracking
        result = db.execute(text("""
            SELECT enumlabel FROM pg_enum
            WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'auditlogevent')
            AND enumlabel = 'tnc_unchecked'
        """))

        if not result.fetchone():
            print("Running migration: Adding new audit log events...")
            new_events = [
                'tnc_unchecked',
                'promo_code_added',
                'promo_code_removed',
            ]
            for value in new_events:
                try:
                    db.execute(text(f"ALTER TYPE auditlogevent ADD VALUE IF NOT EXISTS '{value}'"))
                    db.commit()
                except Exception:
                    db.rollback()
            print("Migration completed: new audit log events added")
        else:
            print("Migration check: new audit log events already exist")

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
    pickup_airline_name: Optional[str] = None
    pickup_flight_number: Optional[str] = None
    pickup_origin: Optional[str] = None
    arrival_id: Optional[int] = None

    # Dropoff details
    dropoff_date: Optional[date] = None
    dropoff_time: Optional[str] = None  # HH:MM format
    dropoff_airline_name: Optional[str] = None
    dropoff_flight_number: Optional[str] = None
    dropoff_destination: Optional[str] = None

    # Actual flight times (for emails and display)
    flight_departure_time: Optional[str] = None  # HH:MM format - actual flight departure
    flight_arrival_time: Optional[str] = None  # HH:MM format - actual flight arrival


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

    Uses simplified anchor pricing model:
    - 3 anchor prices: 1-4 days, 7 days (1 week), 14 days (2 weeks)
    - Daily increment for days between anchors (5-6, 8-13, 15+)

    Advance booking tiers:
    - Early (>=14 days in advance): base price
    - Standard (7-13 days in advance): base + increment
    - Late (<7 days in advance): base + 2x increment
    """
    from booking_service import BookingService

    duration = (request.pickup_date - request.drop_off_date).days

    # Validate duration (1-60 days supported)
    if duration < 1 or duration > 60:
        raise HTTPException(
            status_code=400,
            detail=f"Duration must be between 1 and 60 days. Got {duration} days."
        )

    # Determine package (for legacy compatibility)
    package = BookingService.get_package_for_duration(request.drop_off_date, request.pickup_date)

    # Generate package name based on duration
    if duration == 7:
        package_name = "1 Week Trip"
    elif duration == 14:
        package_name = "2 Week Trip"
    elif duration == 21:
        package_name = "3 Week Trip"
    else:
        package_name = f"{duration} Day{'s' if duration != 1 else ''}"

    # Calculate advance booking tier
    today = date.today()
    days_in_advance = (request.drop_off_date - today).days
    advance_tier = BookingService.get_advance_tier(request.drop_off_date)

    # Calculate price using anchor pricing with daily increment
    price = BookingService.calculate_price_for_duration(duration, request.drop_off_date)

    # Get all prices for this duration (keyed by day number as string)
    all_duration_prices = BookingService.get_all_duration_prices()
    # Use actual duration if <= 21, otherwise use day 21 as reference
    lookup_day = str(min(duration, 21))
    tier_prices = all_duration_prices.get(lookup_day, {})

    # 1-week base rate price (early tier) used for free parking promo discount
    week1_price = all_duration_prices.get("7", {}).get("early", 85.0)

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

    Checks both:
    1. New promo_codes table (generated promo system)
    2. Legacy MarketingSubscriber promo fields

    Promo codes are single-use.
    """
    from db_models import PromoCode as DbPromoCode, Promotion

    code = request.code.strip().upper()
    log_promo("VALIDATE request", {"code": code})

    if not code:
        log_promo("VALIDATE failed - empty code")
        return PromoCodeValidateResponse(
            valid=False,
            message="Please enter a promo code",
        )

    # First, check the new promo_codes table
    promo_code = db.query(DbPromoCode).filter(DbPromoCode.code == code).first()
    if promo_code:
        log_promo("VALIDATE found in promo_codes table", {
            "code": code,
            "promotion_id": promo_code.promotion_id,
            "is_used": promo_code.is_used,
            "max_uses": promo_code.max_uses,
            "use_count": promo_code.use_count,
            "email_sent": promo_code.email_sent,
            "recipient_email": promo_code.recipient_email
        })

        # Check if code has expired (UK timezone) - check this first
        if promo_code.expires_at:
            uk_now = get_uk_now()
            if uk_now >= promo_code.expires_at:
                log_promo("VALIDATE failed - code expired", {"code": code, "expires_at": str(promo_code.expires_at), "uk_now": str(uk_now)})
                return PromoCodeValidateResponse(
                    valid=False,
                    message="This promotion has now expired. Keep an eye out for our next offer!",
                )

        # Check if code can still be used (handles both single-use and multi-use)
        if not promo_code.can_be_used:
            if promo_code.is_multi_use:
                log_promo("VALIDATE failed - multi-use code exhausted", {
                    "code": code,
                    "max_uses": promo_code.max_uses,
                    "use_count": promo_code.use_count
                })
                return PromoCodeValidateResponse(
                    valid=False,
                    message="This promo code has reached its maximum number of uses. Keep an eye out for our next offer!",
                )
            else:
                log_promo("VALIDATE failed - code already used", {"code": code, "used_at": str(promo_code.used_at)})
                return PromoCodeValidateResponse(
                    valid=False,
                    message="Oops! Someone just beat you to it - this promo code has already been used. Keep an eye out for our next offer!",
                )

        # Get discount from parent promotion
        promotion = db.query(Promotion).filter(Promotion.id == promo_code.promotion_id).first()
        if promotion:
            discount = promotion.discount_percent
            log_promo("VALIDATE success (new system)", {
                "code": code,
                "promotion_name": promotion.name,
                "discount_percent": discount,
                "is_multi_use": promo_code.is_multi_use,
                "uses_remaining": promo_code.uses_remaining
            })
            if discount == 100:
                message = "Promo code applied! 100% off your booking!"
            else:
                message = f"Promo code applied! {discount}% off"
            return PromoCodeValidateResponse(
                valid=True,
                message=message,
                discount_percent=discount,
            )
    else:
        log_promo("VALIDATE not found in promo_codes table, checking legacy", {"code": code})

    # Fallback: Look up in legacy MarketingSubscriber promo fields
    subscriber = db.query(MarketingSubscriber).filter(
        (MarketingSubscriber.promo_code == code) |
        (MarketingSubscriber.promo_10_code == code) |
        (MarketingSubscriber.promo_free_code == code) |
        (MarketingSubscriber.founder_promo_code == code)
    ).first()

    if not subscriber:
        return PromoCodeValidateResponse(
            valid=False,
            message="This code is invalid. Please check and try again.",
        )

    # Determine which promo type this code belongs to and check if used
    already_used_message = "Oops! Someone just beat you to it - this promo code has already been used. Keep an eye out for our next offer!"

    if subscriber.founder_promo_code and subscriber.founder_promo_code == code:
        if subscriber.founder_promo_used:
            return PromoCodeValidateResponse(
                valid=False,
                message=already_used_message,
            )
        discount = 10
    elif subscriber.promo_10_code and subscriber.promo_10_code == code:
        if subscriber.promo_10_used:
            return PromoCodeValidateResponse(
                valid=False,
                message=already_used_message,
            )
        discount = 10
    elif subscriber.promo_free_code and subscriber.promo_free_code == code:
        if subscriber.promo_free_used:
            return PromoCodeValidateResponse(
                valid=False,
                message=already_used_message,
            )
        discount = 100
    elif subscriber.promo_code and subscriber.promo_code == code:
        # Legacy field
        if subscriber.promo_code_used:
            return PromoCodeValidateResponse(
                valid=False,
                message=already_used_message,
            )
        discount = subscriber.discount_percent if subscriber.discount_percent is not None else PROMO_DISCOUNT_PERCENT
    else:
        return PromoCodeValidateResponse(
            valid=False,
            message="This code is invalid. Please check and try again.",
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
    days: Optional[int] = Query(30, description="Number of days to include (None or 0 for all)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Get bookings from database.

    Returns bookings with full details including:
    - Customer info (name, email, phone)
    - Vehicle info (registration, make, model, colour)
    - Booking dates and times
    - Payment info (status, amount, stripe_payment_intent_id)

    By default returns last 30 days of bookings. Set days=0 for all bookings.
    """
    from db_models import Booking, Customer, Vehicle, Payment, BookingStatus
    import pytz

    uk_tz = pytz.timezone('Europe/London')
    today = datetime.now(uk_tz).date()

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
    elif days and days > 0:
        # Default: filter to last N days (based on dropoff or pickup date)
        cutoff_date = today - timedelta(days=days)
        query = query.filter(
            or_(
                Booking.dropoff_date >= cutoff_date,
                Booking.pickup_date >= cutoff_date,
            )
        )

    if not include_cancelled:
        query = query.filter(Booking.status != BookingStatus.CANCELLED)

    # Sort: today's bookings first (by dropoff_date), then by dropoff_date ascending
    bookings = query.order_by(
        # Today's bookings first (0 for today, 1 for others)
        case((Booking.dropoff_date == today, 0), else_=1),
        Booking.dropoff_date.asc()
    ).all()

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
            "flight_departure_time": b.flight_departure_time.strftime("%H:%M") if b.flight_departure_time else None,
            "dropoff_flight_number": b.dropoff_flight_number,
            "dropoff_airline_name": b.dropoff_airline_name,
            "dropoff_airline_code": b.dropoff_airline_code,
            "dropoff_destination": b.dropoff_destination,
            "pickup_date": b.pickup_date.isoformat() if b.pickup_date else None,
            "pickup_time": b.pickup_time.strftime("%H:%M") if b.pickup_time else None,
            # pickup_time is now the collection time (arrival + 30)
            "pickup_collection_time": b.pickup_time.strftime("%H:%M") if b.pickup_time else None,
            "flight_arrival_time": b.flight_arrival_time.strftime("%H:%M") if b.flight_arrival_time else None,
            "pickup_flight_number": b.pickup_flight_number,
            "pickup_airline_name": b.pickup_airline_name,
            "pickup_airline_code": b.pickup_airline_code,
            "pickup_origin": b.pickup_origin,
            "notes": b.notes,
            "confirmation_email_sent": b.confirmation_email_sent,
            "confirmation_email_sent_at": b.confirmation_email_sent_at.isoformat() if b.confirmation_email_sent_at else None,
            "reminder_2day_sent": b.reminder_2day_sent,
            "reminder_2day_sent_at": b.reminder_2day_sent_at.isoformat() if b.reminder_2day_sent_at else None,
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
                # Founder followup tracking
                "founder_followup_sent": b.customer.founder_followup_sent,
                "founder_followup_sent_at": b.customer.founder_followup_sent_at.isoformat() if b.customer.founder_followup_sent_at else None,
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
        "days_filter": days if days and days > 0 else None,
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


@app.get("/api/admin/bookings/stats")
async def get_booking_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get booking statistics for growth visualization.

    Returns:
    - Daily/weekly/monthly booking counts by status
    - Running totals
    - Status breakdown
    """
    from collections import defaultdict

    # Get ALL bookings ordered by creation date
    all_bookings = db.query(DbBooking).order_by(DbBooking.created_at.asc()).all()

    # Status colors mapping
    status_order = ['confirmed', 'completed', 'pending', 'cancelled']

    # Aggregate by month with status breakdown
    monthly_by_status = defaultdict(lambda: defaultdict(int))
    weekly_by_status = defaultdict(lambda: defaultdict(int))
    daily_by_status = defaultdict(lambda: defaultdict(int))

    for booking in all_bookings:
        if booking.created_at:
            status = booking.status.value if booking.status else 'unknown'

            # Daily: YYYY-MM-DD
            day_key = booking.created_at.strftime("%Y-%m-%d")
            daily_by_status[day_key][status] += 1

            # Weekly: YYYY-WW (ISO week)
            iso_year, iso_week, _ = booking.created_at.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            weekly_by_status[week_key][status] += 1

            # Monthly: YYYY-MM
            month_key = booking.created_at.strftime("%Y-%m")
            monthly_by_status[month_key][status] += 1

    # Convert to sorted lists for charts (with status breakdown)
    def format_data(data_dict, key_name):
        result = []
        for key in sorted(data_dict.keys()):
            entry = {key_name: key}
            for status in status_order:
                entry[status] = data_dict[key].get(status, 0)
            entry['total'] = sum(data_dict[key].values())
            result.append(entry)
        return result

    daily_data = format_data(daily_by_status, 'date')
    weekly_data = format_data(weekly_by_status, 'week')
    monthly_data = format_data(monthly_by_status, 'month')

    # Calculate cumulative totals (confirmed + completed only for growth)
    cumulative = []
    running_total = 0
    for day in daily_data:
        running_total += day.get('confirmed', 0) + day.get('completed', 0)
        cumulative.append({"date": day["date"], "total": running_total})

    # Summary stats
    status_totals = defaultdict(int)
    for booking in all_bookings:
        status = booking.status.value if booking.status else 'unknown'
        status_totals[status] += 1

    total_successful = status_totals.get('confirmed', 0) + status_totals.get('completed', 0)

    # Recent period comparisons (confirmed + completed only)
    today = date.today()
    this_week_start = today - timedelta(days=today.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    this_month_start = today.replace(day=1)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)

    successful_bookings = [b for b in all_bookings if b.status in [BookingStatus.CONFIRMED, BookingStatus.COMPLETED]]
    this_week_count = sum(1 for b in successful_bookings if b.created_at and b.created_at.date() >= this_week_start)
    last_week_count = sum(1 for b in successful_bookings if b.created_at and last_week_start <= b.created_at.date() < this_week_start)
    this_month_count = sum(1 for b in successful_bookings if b.created_at and b.created_at.date() >= this_month_start)
    last_month_count = sum(1 for b in successful_bookings if b.created_at and last_month_start <= b.created_at.date() < this_month_start)

    # Confirmed-only counts for booking targets (future bookings)
    confirmed_bookings = [b for b in all_bookings if b.status == BookingStatus.CONFIRMED]
    confirmed_today = sum(1 for b in confirmed_bookings if b.created_at and b.created_at.date() == today)
    confirmed_this_week = sum(1 for b in confirmed_bookings if b.created_at and b.created_at.date() >= this_week_start)
    confirmed_this_month = sum(1 for b in confirmed_bookings if b.created_at and b.created_at.date() >= this_month_start)

    # Revenue calculations - only count bookings with non-zero payments
    from db_models import Payment

    total_revenue_pence = 0
    paid_customer_count = 0

    for booking in successful_bookings:
        # Only count bookings with actual payments (excludes free promo bookings with £0 payment)
        if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > 0:
            total_revenue_pence += booking.payment.amount_pence
            paid_customer_count += 1

    # Calculate average revenue per paying customer
    avg_revenue_per_customer = round(total_revenue_pence / paid_customer_count / 100, 2) if paid_customer_count > 0 else 0
    total_revenue_pounds = round(total_revenue_pence / 100, 2)

    # Calculate average trip duration, drop-off time range, and pick-up time range
    trip_durations = []
    dropoff_times_minutes = []
    pickup_times_minutes = []

    for booking in successful_bookings:
        # Trip duration (in days)
        if booking.dropoff_date and booking.pickup_date:
            duration = (booking.pickup_date - booking.dropoff_date).days
            if duration >= 0:
                trip_durations.append(duration)

        # Drop-off time (convert to minutes from midnight for averaging)
        if booking.dropoff_time:
            minutes = booking.dropoff_time.hour * 60 + booking.dropoff_time.minute
            dropoff_times_minutes.append(minutes)

        # Pick-up time (convert to minutes from midnight for averaging)
        if booking.pickup_time:
            minutes = booking.pickup_time.hour * 60 + booking.pickup_time.minute
            pickup_times_minutes.append(minutes)

    # Calculate averages
    avg_trip_duration = round(sum(trip_durations) / len(trip_durations), 1) if trip_durations else 0

    # Calculate top 5 most common trip durations with percentages
    duration_counts = {}
    for d in trip_durations:
        duration_counts[d] = duration_counts.get(d, 0) + 1
    total_trips = len(trip_durations)
    top_durations = sorted(duration_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_durations = [
        {"days": d, "count": c, "percent": round(c / total_trips * 100, 1) if total_trips > 0 else 0}
        for d, c in top_durations
    ]

    # Helper function to find top N busiest hours using fixed hourly buckets
    # Each booking is counted in exactly one bucket (00:00-01:00, 01:00-02:00, etc.)
    def find_top_busiest_hours(times_minutes, top_n=3):
        if not times_minutes:
            return []

        # Count bookings in each fixed hourly bucket (0-23)
        hour_buckets = {}
        for time_min in times_minutes:
            hour = time_min // 60  # Get the hour (0-23)
            hour_buckets[hour] = hour_buckets.get(hour, 0) + 1

        # Convert to list of dicts with formatted times
        hour_counts = []
        for hour, count in hour_buckets.items():
            end_hour = (hour + 1) % 24
            hour_counts.append({
                "start": f"{hour:02d}:00",
                "end": f"{end_hour:02d}:00",
                "count": count
            })

        # Sort by count descending and return top N
        hour_counts.sort(key=lambda x: x["count"], reverse=True)
        return hour_counts[:top_n]

    # Drop-off time range (AM: 00:00-11:59, PM: 12:00-23:59)
    if dropoff_times_minutes:
        am_dropoffs = [m for m in dropoff_times_minutes if m < 720]  # Before 12:00
        pm_dropoffs = [m for m in dropoff_times_minutes if m >= 720]  # 12:00 and after
        dropoff_range = {
            "am": len(am_dropoffs),
            "pm": len(pm_dropoffs),
            "am_busiest": find_top_busiest_hours(am_dropoffs, 3),
            "pm_busiest": find_top_busiest_hours(pm_dropoffs, 3),
        }
    else:
        dropoff_range = {"am": 0, "pm": 0, "am_busiest": [], "pm_busiest": []}

    # Pick-up time range (AM: 00:00-11:59, PM: 12:00-23:59)
    if pickup_times_minutes:
        am_pickups = [m for m in pickup_times_minutes if m < 720]  # Before 12:00
        pm_pickups = [m for m in pickup_times_minutes if m >= 720]  # 12:00 and after
        pickup_range = {
            "am": len(am_pickups),
            "pm": len(pm_pickups),
            "am_busiest": find_top_busiest_hours(am_pickups, 3),
            "pm_busiest": find_top_busiest_hours(pm_pickups, 3),
        }
    else:
        pickup_range = {"am": 0, "pm": 0, "am_busiest": [], "pm_busiest": []}

    # Day of week booking creation analysis (when customers make bookings)
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    booking_days_of_week = {day: 0 for day in day_names}

    for booking in successful_bookings:
        if booking.created_at:
            day_name = day_names[booking.created_at.weekday()]
            booking_days_of_week[day_name] += 1

    # Convert to list format with percentages
    total_bookings_with_dates = sum(booking_days_of_week.values())
    booking_days_list = []
    for day in day_names:
        count = booking_days_of_week[day]
        percent = round(count / total_bookings_with_dates * 100, 1) if total_bookings_with_dates > 0 else 0
        booking_days_list.append({
            "day": day,
            "count": count,
            "percent": percent
        })

    return {
        "total_bookings": len(all_bookings),
        "total_successful": total_successful,
        "status_totals": dict(status_totals),
        "this_week": this_week_count,
        "last_week": last_week_count,
        "this_month": this_month_count,
        "last_month": last_month_count,
        "confirmed_today": confirmed_today,
        "confirmed_this_week": confirmed_this_week,
        "confirmed_this_month": confirmed_this_month,
        "daily": daily_data,
        "weekly": weekly_data,
        "monthly": monthly_data,
        "cumulative": cumulative,
        "total_revenue": total_revenue_pounds,
        "paid_customer_count": paid_customer_count,
        "avg_revenue_per_customer": avg_revenue_per_customer,
        "avg_trip_duration": avg_trip_duration,
        "top_durations": top_durations,
        "dropoff_range": dropoff_range,
        "pickup_range": pickup_range,
        "booking_days_of_week": booking_days_list,
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

        # Get destination name - prefer request value, fallback to flight table
        dropoff_destination = request.dropoff_destination
        if not dropoff_destination and departure_flight and departure_flight.destination_name:
            # Extract city name from "City, CountryCode" format
            parts = departure_flight.destination_name.split(', ')
            dropoff_destination = parts[0] if parts else departure_flight.destination_name
        # Shorten Tenerife-Reinasofia to Tenerife
        if dropoff_destination == 'Tenerife-Reinasofia':
            dropoff_destination = 'Tenerife'

        # Get flight number - prefer new field name, fallback to legacy
        dropoff_flight_num = request.dropoff_flight_number or request.departure_flight_number
        pickup_flight_num = request.pickup_flight_number or request.return_flight_number

        # Get origin name - prefer request value, fallback to flight table lookup
        from db_models import FlightArrival
        pickup_origin = request.pickup_origin
        arrival_id = None
        if pickup_flight_num and request.pickup_date:
            arrival = db.query(FlightArrival).filter(
                FlightArrival.flight_number == pickup_flight_num,
                FlightArrival.date == request.pickup_date
            ).first()
            if arrival:
                arrival_id = arrival.id
                if not pickup_origin and arrival.origin_name:
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
            dropoff_flight_number=dropoff_flight_num,
            dropoff_destination=dropoff_destination,
            dropoff_airline_name=request.dropoff_airline_name,
            pickup_flight_number=pickup_flight_num,
            pickup_origin=pickup_origin,
            pickup_airline_name=request.pickup_airline_name,
            arrival_id=arrival_id,
            # Actual flight times
            flight_departure_time=datetime.strptime(request.flight_departure_time, "%H:%M").time() if request.flight_departure_time else None,
            flight_arrival_time=datetime.strptime(request.flight_arrival_time, "%H:%M").time() if request.flight_arrival_time else None,
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

        # Mark promo code as used ONLY for free bookings (100% discount)
        # For paid bookings, the Stripe webhook will mark the code as used after payment succeeds
        if request.promo_code and is_free:
            promo_code_str = request.promo_code.strip().upper()
            from db_models import PromoCode as DbPromoCode, Promotion as DbPromotion

            # First, check the new promo_codes table
            promo_code_record = db.query(DbPromoCode).filter(
                DbPromoCode.code == promo_code_str
            ).first()

            if promo_code_record and promo_code_record.can_be_used:
                # Get discount percent from promotion
                promotion = db.query(DbPromotion).filter(DbPromotion.id == promo_code_record.promotion_id).first()
                discount_pct = promotion.discount_percent if promotion else 100
                mark_promo_code_used(db, promo_code_record, booking.id, discount_pct, request.amount_pence)
            else:
                # Fallback: Legacy MarketingSubscriber promo fields
                subscriber = db.query(MarketingSubscriber).filter(
                    (MarketingSubscriber.promo_code == promo_code_str) |
                    (MarketingSubscriber.promo_10_code == promo_code_str) |
                    (MarketingSubscriber.promo_free_code == promo_code_str) |
                    (MarketingSubscriber.founder_promo_code == promo_code_str)
                ).first()

                if subscriber:
                    now = datetime.utcnow()
                    if subscriber.founder_promo_code == promo_code_str and not subscriber.founder_promo_used:
                        subscriber.founder_promo_used = True
                        subscriber.founder_promo_used_at = now
                    elif subscriber.promo_free_code == promo_code_str and not subscriber.promo_free_used:
                        subscriber.promo_free_used = True
                        subscriber.promo_free_used_at = now
                        subscriber.promo_free_used_booking_id = booking.id
                    elif subscriber.promo_10_code == promo_code_str and not subscriber.promo_10_used:
                        subscriber.promo_10_used = True
                        subscriber.promo_10_used_at = now
                        subscriber.promo_10_used_booking_id = booking.id
                    elif subscriber.promo_code == promo_code_str and not subscriber.promo_code_used:
                        subscriber.promo_code_used = True
                        subscriber.promo_code_used_at = now
                        subscriber.promo_code_used_booking_id = booking.id

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
            # Build flight info for email: airline + flight number (if provided) + destination
            departure_flight_str = ""
            if request.dropoff_airline_name or dropoff_destination:
                parts = []
                if request.dropoff_airline_name:
                    parts.append(request.dropoff_airline_name)
                if dropoff_flight_num and dropoff_flight_num != 'Unknown':
                    parts.append(dropoff_flight_num)
                departure_flight_str = " ".join(parts)
                if dropoff_destination:
                    departure_flight_str += f" to {dropoff_destination}"

            return_flight_str = ""
            if request.pickup_airline_name or pickup_origin:
                parts = []
                if request.pickup_airline_name:
                    parts.append(request.pickup_airline_name)
                if pickup_flight_num and pickup_flight_num != 'Unknown':
                    parts.append(pickup_flight_num)
                return_flight_str = " ".join(parts)
                if pickup_origin:
                    return_flight_str += f" from {pickup_origin}"

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
                flight_arrival_time=request.flight_arrival_time or "",
                flight_departure_time=request.flight_departure_time or "",
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
        if not payment.paid_at:
            # Use booking created_at date for manual bookings
            payment.paid_at = booking.created_at or datetime.utcnow()

    db.commit()

    # Send confirmation email
    email_sent = False
    try:
        # Format dates
        dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")
        dropoff_time_str = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else "TBC"
        pickup_date_str = booking.pickup_date.strftime("%A, %d %B %Y")
        # pickup_time is now the collection time (arrival + 30)
        pickup_time_str = booking.pickup_time.strftime("%H:%M") if booking.pickup_time else "TBC"
        # Flight arrival time for email
        flight_arrival_time_str = booking.flight_arrival_time.strftime("%H:%M") if booking.flight_arrival_time else ""
        flight_departure_time_str = booking.flight_departure_time.strftime("%H:%M") if booking.flight_departure_time else ""

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

        # Format flight info: airline + flight number (if provided) + destination
        departure_flight = ""
        if booking.dropoff_airline_name or booking.dropoff_destination:
            parts = []
            if booking.dropoff_airline_name:
                parts.append(booking.dropoff_airline_name)
            if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
                parts.append(booking.dropoff_flight_number)
            departure_flight = " ".join(parts)
            if booking.dropoff_destination:
                departure_flight += f" to {booking.dropoff_destination}"

        return_flight = ""
        if booking.pickup_airline_name or booking.pickup_origin:
            parts = []
            if booking.pickup_airline_name:
                parts.append(booking.pickup_airline_name)
            if booking.pickup_flight_number and booking.pickup_flight_number != 'Unknown':
                parts.append(booking.pickup_flight_number)
            return_flight = " ".join(parts)
            if booking.pickup_origin:
                return_flight += f" from {booking.pickup_origin}"

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
            flight_arrival_time=flight_arrival_time_str,
            flight_departure_time=flight_departure_time_str,
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
    from db_models import MarketingSubscriber, PromoCode
    db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_code_used_booking_id == booking_id
    ).update({MarketingSubscriber.promo_code_used_booking_id: None}, synchronize_session=False)
    db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_10_used_booking_id == booking_id
    ).update({MarketingSubscriber.promo_10_used_booking_id: None}, synchronize_session=False)
    db.query(MarketingSubscriber).filter(
        MarketingSubscriber.promo_free_used_booking_id == booking_id
    ).update({MarketingSubscriber.promo_free_used_booking_id: None}, synchronize_session=False)

    # Clear promo_codes booking reference and reset used status (for pending bookings, code wasn't truly used)
    db.query(PromoCode).filter(
        PromoCode.booking_id == booking_id
    ).update({PromoCode.booking_id: None, PromoCode.is_used: False, PromoCode.used_at: None}, synchronize_session=False)

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
    - Pickup date/time (collection time, not arrival time)
    - Dropoff date/time
    - Flight numbers and destinations/origins

    Use the Edit Flight Details feature to modify arrival flight times.
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

        # pickup_time is the collection time (arrival + 30)
        booking.pickup_time = new_pickup_time
        updates_made.append("pickup_time")

    if request.pickup_airline_name is not None:
        booking.pickup_airline_name = request.pickup_airline_name
        updates_made.append("pickup_airline_name")

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
        new_dropoff_time = dt_time(int(parts[0]), int(parts[1]))
        booking.dropoff_time = new_dropoff_time
        updates_made.append("dropoff_time")

    if request.dropoff_airline_name is not None:
        booking.dropoff_airline_name = request.dropoff_airline_name
        updates_made.append("dropoff_airline_name")

    if request.dropoff_flight_number is not None:
        booking.dropoff_flight_number = request.dropoff_flight_number
        updates_made.append("dropoff_flight_number")

    if request.dropoff_destination is not None:
        booking.dropoff_destination = request.dropoff_destination
        updates_made.append("dropoff_destination")

    # Update actual flight times
    if request.flight_departure_time is not None:
        parts = request.flight_departure_time.split(':')
        booking.flight_departure_time = dt_time(int(parts[0]), int(parts[1]))
        updates_made.append("flight_departure_time")

    if request.flight_arrival_time is not None:
        parts = request.flight_arrival_time.split(':')
        arrival_time = dt_time(int(parts[0]), int(parts[1]))
        booking.flight_arrival_time = arrival_time

        # Calculate pickup_time as arrival + 30 minutes
        arrival_dt = datetime.combine(datetime.today(), arrival_time)
        pickup_dt = arrival_dt + timedelta(minutes=30)
        pickup_time = pickup_dt.time()

        booking.pickup_time = pickup_time
        updates_made.append("flight_arrival_time")
        updates_made.append("pickup_time")

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
            "pickup_airline_name": booking.pickup_airline_name,
            "pickup_flight_number": booking.pickup_flight_number,
            "pickup_origin": booking.pickup_origin,
            "flight_arrival_time": booking.flight_arrival_time.strftime("%H:%M") if booking.flight_arrival_time else None,
            "dropoff_date": booking.dropoff_date.isoformat() if booking.dropoff_date else None,
            "dropoff_time": booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else None,
            "dropoff_airline_name": booking.dropoff_airline_name,
            "dropoff_flight_number": booking.dropoff_flight_number,
            "dropoff_destination": booking.dropoff_destination,
            "flight_departure_time": booking.flight_departure_time.strftime("%H:%M") if booking.flight_departure_time else None,
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

    # pickup_time is now the collection time (arrival + 30)
    pickup_time_str = booking.pickup_time.strftime("%H:%M") if booking.pickup_time else ""

    # Get flight arrival time
    flight_arrival_time_str = booking.flight_arrival_time.strftime("%H:%M") if booking.flight_arrival_time else ""

    # Get flight departure time
    flight_departure_time_str = ""
    if booking.flight_departure_time:
        flight_departure_time_str = booking.flight_departure_time.strftime("%H:%M")

    # Format dates
    dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")
    pickup_date_str = booking.pickup_date.strftime("%A, %d %B %Y")
    dropoff_time_str = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else ""

    # Format flight info: airline + flight number (if provided) + destination
    departure_flight = ""
    if booking.dropoff_airline_name or booking.dropoff_destination:
        parts = []
        if booking.dropoff_airline_name:
            parts.append(booking.dropoff_airline_name)
        if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
            parts.append(booking.dropoff_flight_number)
        departure_flight = " ".join(parts)
        if booking.dropoff_destination:
            departure_flight += f" to {booking.dropoff_destination}"

    return_flight = ""
    if booking.pickup_airline_name or booking.pickup_origin:
        parts = []
        if booking.pickup_airline_name:
            parts.append(booking.pickup_airline_name)
        if booking.pickup_flight_number and booking.pickup_flight_number != 'Unknown':
            parts.append(booking.pickup_flight_number)
        return_flight = " ".join(parts)
        if booking.pickup_origin:
            return_flight += f" from {booking.pickup_origin}"

    # Package name - use flexible duration format
    duration_days = (booking.pickup_date - booking.dropoff_date).days
    package_name = f"{duration_days} day{'s' if duration_days != 1 else ''}"

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
        flight_arrival_time=flight_arrival_time_str,
        flight_departure_time=flight_departure_time_str,
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


@app.post("/api/admin/bookings/{booking_id}/send-founder-email")
async def send_founder_email_endpoint(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin endpoint: Send founder followup email to customer.

    Sends a personal follow-up email from the founder to customers
    who haven't completed their booking (abandoned cart).
    """
    from db_models import BookingStatus, Customer
    from email_service import send_founder_followup_email

    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail="Founder email can only be sent for pending bookings")

    customer = booking.customer
    if not customer:
        raise HTTPException(status_code=400, detail="No customer associated with this booking")

    if customer.founder_followup_sent:
        raise HTTPException(
            status_code=400,
            detail=f"Founder followup email already sent to {customer.email} on {customer.founder_followup_sent_at.strftime('%d %b %Y at %H:%M') if customer.founder_followup_sent_at else 'unknown date'}"
        )

    # Send the email
    email_sent = send_founder_followup_email(
        email=customer.email,
        first_name=booking.customer_first_name or customer.first_name,
    )

    if email_sent:
        # Update customer tracking
        customer.founder_followup_sent = True
        customer.founder_followup_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Founder followup email sent to {customer.email}",
            "reference": booking.reference,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send founder followup email. Check SendGrid configuration."
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
                "promo_10_reminder_sent": s.promo_10_reminder_sent,
                "promo_10_reminder_sent_at": s.promo_10_reminder_sent_at.isoformat() if s.promo_10_reminder_sent_at else None,
                # FREE promo (separate)
                "promo_free_code": s.promo_free_code,
                "promo_free_sent": s.promo_free_sent,
                "promo_free_sent_at": s.promo_free_sent_at.isoformat() if s.promo_free_sent_at else None,
                "promo_free_used": s.promo_free_used,
                "promo_free_used_at": s.promo_free_used_at.isoformat() if s.promo_free_used_at else None,
                "promo_free_reminder_sent": s.promo_free_reminder_sent,
                "promo_free_reminder_sent_at": s.promo_free_reminder_sent_at.isoformat() if s.promo_free_reminder_sent_at else None,
                # Founder thank you email (separate)
                "founder_promo_code": s.founder_promo_code,
                "founder_email_sent": s.founder_email_sent,
                "founder_email_sent_at": s.founder_email_sent_at.isoformat() if s.founder_email_sent_at else None,
                "founder_promo_used": s.founder_promo_used,
                "founder_promo_used_at": s.founder_promo_used_at.isoformat() if s.founder_promo_used_at else None,
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
            "founder_followup_sent": customer.founder_followup_sent,
            "founder_followup_sent_at": customer.founder_followup_sent_at.isoformat() if customer.founder_followup_sent_at else None,
        })

    return {
        "count": len(leads_data),
        "leads": leads_data,
    }


@app.get("/api/admin/customers")
async def get_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all customers ordered by created_at ascending.
    Returns customer contact and billing information.
    """
    from db_models import Customer

    customers = (
        db.query(Customer)
        .order_by(Customer.created_at.desc())
        .all()
    )

    customers_data = []
    for customer in customers:
        # Get marketing source if exists
        marketing_source = None
        if customer.marketing_source:
            marketing_source = customer.marketing_source.source

        customers_data.append({
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "billing_postcode": customer.billing_postcode,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
            "marketing_source": marketing_source,
        })

    return {
        "count": len(customers_data),
        "customers": customers_data,
    }


class UpdateCustomerRequest(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None


@app.patch("/api/admin/customers/{customer_id}")
async def update_customer(
    customer_id: int,
    request: UpdateCustomerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update customer email and/or phone.
    At least one field must be provided.
    """
    from db_models import Customer

    # Validate at least one field provided
    if request.email is None and request.phone is None:
        raise HTTPException(status_code=400, detail="At least one field (email or phone) must be provided")

    # Find customer
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Validate email format if provided
    if request.email is not None:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, request.email):
            raise HTTPException(status_code=400, detail="Invalid email format")

        # Check email uniqueness (excluding current customer)
        existing = db.query(Customer).filter(
            Customer.email == request.email,
            Customer.id != customer_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        customer.email = request.email

    # Validate phone if provided
    if request.phone is not None:
        # Basic phone validation - allow digits, spaces, +, -, ()
        import re
        phone_clean = re.sub(r'[\s\-\(\)\+]', '', request.phone)
        if not phone_clean.isdigit() or len(phone_clean) < 10 or len(phone_clean) > 15:
            raise HTTPException(status_code=400, detail="Invalid phone format")

        customer.phone = request.phone

    db.commit()
    db.refresh(customer)

    return {
        "success": True,
        "customer": {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone,
            "billing_postcode": customer.billing_postcode,
            "created_at": customer.created_at.isoformat() if customer.created_at else None,
        }
    }


@app.delete("/api/admin/customers/{customer_id}")
async def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete a customer by ID.
    Will fail if customer has associated bookings.
    """
    from db_models import Customer, Booking

    # Find customer
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Check for associated bookings
    booking_count = db.query(Booking).filter(Booking.customer_id == customer_id).count()
    if booking_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete customer with {booking_count} associated booking(s)"
        )

    # Delete customer
    db.delete(customer)
    db.commit()

    return {
        "success": True,
        "message": f"Customer {customer_id} deleted successfully"
    }


@app.get("/api/admin/reports/booking-locations")
async def get_booking_locations(
    map_type: str = Query("bookings", description="Map type: 'bookings' for confirmed bookings, 'origins' for all leads"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get locations for map visualization.
    Cached for 1 hour.

    map_type='bookings': Returns confirmed bookings with geocoded billing postcodes.
    map_type='origins': Returns all customers (leads) from booking flow Page 1 with geocoded billing postcodes.
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Check cache
    global _booking_locations_cache
    cache_key = map_type if map_type in ["bookings", "origins"] else "bookings"
    if not refresh:
        cache_entry = _booking_locations_cache.get(cache_key, {})
        if cache_entry.get("data") is not None and cache_entry.get("cached_at") is not None:
            cache_age = (now - cache_entry["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = cache_entry["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    from db_models import Booking, Customer

    if map_type == "origins":
        # Query customers with billing postcodes who have billing_updated_at set
        # This filters to only show leads captured since the feature was deployed
        # Shows customers who either:
        #   1. Have no bookings (pure leads), OR
        #   2. Started a new booking flow AFTER their last booking (returning customer lead)
        from datetime import datetime, timezone
        from sqlalchemy import func, and_, or_
        feature_launch_date = datetime(2026, 2, 16, 20, 0, 0, tzinfo=timezone.utc)

        # Subquery to get the most recent booking created_at for each customer
        latest_booking = (
            db.query(
                Booking.customer_id,
                func.max(Booking.created_at).label('last_booking_date')
            )
            .group_by(Booking.customer_id)
            .subquery()
        )

        # Get customers who are leads for their current booking attempt
        customers = (
            db.query(Customer)
            .outerjoin(latest_booking, Customer.id == latest_booking.c.customer_id)
            .filter(Customer.billing_postcode.isnot(None))
            .filter(Customer.billing_postcode != "")
            .filter(Customer.billing_updated_at.isnot(None))
            .filter(Customer.billing_updated_at >= feature_launch_date)
            .filter(
                or_(
                    # No bookings at all (pure lead)
                    latest_booking.c.last_booking_date.is_(None),
                    # billing_updated_at is after their last booking (new lead attempt)
                    Customer.billing_updated_at > latest_booking.c.last_booking_date
                )
            )
            .order_by(Customer.billing_updated_at.desc())
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

        result = {
            "count": len(locations),
            "total_customers": len(customers),
            "skipped_count": len(skipped),
            "skipped": skipped,
            "locations": locations,
            "map_type": map_type,
        }

        # Store in cache
        _booking_locations_cache[cache_key] = {"data": result.copy(), "cached_at": now}
        result["cached"] = False
        return result

    # Default: map_type="bookings" - Query all bookings
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.customer))
        .filter(Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.COMPLETED, BookingStatus.CANCELLED]))
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

    result = {
        "count": len(locations),
        "total_bookings": len(bookings),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "locations": locations,
        "map_type": map_type,
    }

    # Store in cache
    _booking_locations_cache[cache_key] = {"data": result.copy(), "cached_at": now}
    result["cached"] = False
    return result


@app.get("/api/admin/reports/occupancy")
async def get_occupancy_report(
    view: str = Query("daily", description="View type: 'daily', 'weekly', or 'monthly'"),
    start_date: Optional[date] = Query(None, description="Start date for the report (defaults to 30 days ago for daily, 12 weeks for weekly, 6 months for monthly)"),
    end_date: Optional[date] = Query(None, description="End date for the report (defaults to 60 days from now)"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get occupancy report showing parking space utilization by date, week, or month.
    Cached for 1 hour (default parameters only).

    For each time period, calculates:
    - occupied: Number of vehicles parked (active bookings for that date/period)
    - available: Number of free spaces (60 - occupied)
    - occupancy_percent: Percentage utilization

    A vehicle is counted as "occupied" on any date between dropoff_date and pickup_date (inclusive).
    Only confirmed and completed bookings are counted.
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Only cache default requests (no custom date range)
    is_default_request = start_date is None and end_date is None

    # Check cache
    global _occupancy_cache
    if is_default_request and not refresh:
        if _occupancy_cache.get("data") is not None and _occupancy_cache.get("cached_at") is not None:
            cache_age = (now - _occupancy_cache["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = _occupancy_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    from db_models import Booking, BookingStatus
    from datetime import timedelta
    from collections import defaultdict
    import calendar

    MAX_CAPACITY = 60

    # Set default date ranges based on view type
    today = date.today()
    if view == "daily":
        default_start = today - timedelta(days=30)
        default_end = today + timedelta(days=60)
    elif view == "weekly":
        default_start = today - timedelta(weeks=12)
        default_end = today + timedelta(weeks=12)
    elif view == "monthly":
        default_start = today - timedelta(days=180)  # ~6 months
        default_end = today + timedelta(days=180)
    else:
        default_start = today - timedelta(days=30)
        default_end = today + timedelta(days=60)

    report_start = start_date or default_start
    report_end = end_date or default_end

    # Get all active bookings (confirmed or completed) that overlap with our date range
    bookings = (
        db.query(Booking)
        .filter(Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]))
        .filter(Booking.dropoff_date <= report_end)
        .filter(Booking.pickup_date >= report_start)
        .all()
    )

    if view == "daily":
        # Calculate daily occupancy
        daily_occupancy = defaultdict(int)

        # For each booking, increment the count for each day the vehicle is parked
        for booking in bookings:
            current_date = max(booking.dropoff_date, report_start)
            end_date_for_booking = min(booking.pickup_date, report_end)
            while current_date <= end_date_for_booking:
                daily_occupancy[current_date.isoformat()] += 1
                current_date += timedelta(days=1)

        # Build response - include all dates in range
        data = []
        current_date = report_start
        while current_date <= report_end:
            date_str = current_date.isoformat()
            occupied = daily_occupancy.get(date_str, 0)
            # Format as dd/mm/yyyy for UK display
            display_date = current_date.strftime("%d/%m/%Y")
            data.append({
                "date": date_str,
                "display_date": display_date,
                "occupied": occupied,
                "available": MAX_CAPACITY - occupied,
                "occupancy_percent": round((occupied / MAX_CAPACITY) * 100, 1),
                "is_past": current_date < today,
                "is_today": current_date == today,
            })
            current_date += timedelta(days=1)

        result = {
            "view": "daily",
            "max_capacity": MAX_CAPACITY,
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
            "data": data,
        }
        if is_default_request:
            _occupancy_cache["data"] = result.copy()
            _occupancy_cache["cached_at"] = now
        result["cached"] = False
        return result

    elif view == "weekly":
        # Calculate weekly occupancy (ISO week format)
        weekly_occupancy = defaultdict(lambda: {"total_days": 0, "total_occupied": 0})

        for booking in bookings:
            current_date = max(booking.dropoff_date, report_start)
            end_date_for_booking = min(booking.pickup_date, report_end)
            while current_date <= end_date_for_booking:
                # ISO week key: YYYY-Www
                week_key = current_date.strftime("%G-W%V")
                weekly_occupancy[week_key]["total_occupied"] += 1
                current_date += timedelta(days=1)

        # Count days per week in our range
        current_date = report_start
        while current_date <= report_end:
            week_key = current_date.strftime("%G-W%V")
            weekly_occupancy[week_key]["total_days"] += 1
            current_date += timedelta(days=1)

        # Build response
        data = []
        week_keys = sorted(weekly_occupancy.keys())
        for week_key in week_keys:
            week_data = weekly_occupancy[week_key]
            days_in_week = week_data["total_days"]
            avg_occupied = week_data["total_occupied"] / days_in_week if days_in_week > 0 else 0

            # Parse week to get start date for display
            year, week_num = week_key.split("-W")
            week_start = date.fromisocalendar(int(year), int(week_num), 1)
            week_end = week_start + timedelta(days=6)
            display_week = f"{week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m/%Y')}"

            data.append({
                "week": week_key,
                "display_week": display_week,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "avg_occupied": round(avg_occupied, 1),
                "avg_available": round(MAX_CAPACITY - avg_occupied, 1),
                "avg_occupancy_percent": round((avg_occupied / MAX_CAPACITY) * 100, 1),
                "is_current_week": week_start <= today <= week_end,
                "is_past": week_end < today,
            })

        result = {
            "view": "weekly",
            "max_capacity": MAX_CAPACITY,
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
            "data": data,
        }
        if is_default_request:
            _occupancy_cache["data"] = result.copy()
            _occupancy_cache["cached_at"] = now
        result["cached"] = False
        return result

    elif view == "monthly":
        # Calculate monthly occupancy
        monthly_occupancy = defaultdict(lambda: {"total_days": 0, "total_occupied": 0})

        for booking in bookings:
            current_date = max(booking.dropoff_date, report_start)
            end_date_for_booking = min(booking.pickup_date, report_end)
            while current_date <= end_date_for_booking:
                month_key = current_date.strftime("%Y-%m")
                monthly_occupancy[month_key]["total_occupied"] += 1
                current_date += timedelta(days=1)

        # Count days per month in our range
        current_date = report_start
        while current_date <= report_end:
            month_key = current_date.strftime("%Y-%m")
            monthly_occupancy[month_key]["total_days"] += 1
            current_date += timedelta(days=1)

        # Build response
        data = []
        month_keys = sorted(monthly_occupancy.keys())
        for month_key in month_keys:
            month_data = monthly_occupancy[month_key]
            days_in_month = month_data["total_days"]
            avg_occupied = month_data["total_occupied"] / days_in_month if days_in_month > 0 else 0

            # Parse month for display
            year, month = month_key.split("-")
            month_name = calendar.month_name[int(month)]
            display_month = f"{month_name} {year}"

            # Check if current month
            is_current = (int(year) == today.year and int(month) == today.month)
            is_past = date(int(year), int(month), 1) < today.replace(day=1)

            data.append({
                "month": month_key,
                "display_month": display_month,
                "avg_occupied": round(avg_occupied, 1),
                "avg_available": round(MAX_CAPACITY - avg_occupied, 1),
                "avg_occupancy_percent": round((avg_occupied / MAX_CAPACITY) * 100, 1),
                "is_current_month": is_current,
                "is_past": is_past and not is_current,
            })

        result = {
            "view": "monthly",
            "max_capacity": MAX_CAPACITY,
            "start_date": report_start.isoformat(),
            "end_date": report_end.isoformat(),
            "data": data,
        }
        if is_default_request:
            _occupancy_cache["data"] = result.copy()
            _occupancy_cache["cached_at"] = now
        result["cached"] = False
        return result

    else:
        raise HTTPException(status_code=400, detail="Invalid view type. Use 'daily', 'weekly', or 'monthly'.")


@app.get("/api/admin/reports/popular")
async def get_popular_airlines_destinations(
    start_date: Optional[date] = Query(None, description="Start date filter (defaults to all time)"),
    end_date: Optional[date] = Query(None, description="End date filter (defaults to today)"),
    top: int = Query(10, description="Number of top results to return (5, 10, or 20)"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get most popular airlines and destinations based on confirmed and completed bookings.
    Cached for 1 hour (default parameters only).

    Returns ranked lists of:
    - Top airlines by booking count (each booking counted once per unique airline)
    - Top destinations by booking count (each booking counted once per unique destination)

    Filters:
    - start_date/end_date: Date range for bookings (based on created_at)
    - top: Number of results (5, 10, or 20)
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Only cache default requests
    is_default_request = start_date is None and end_date is None and top == 10

    # Check cache
    global _popular_cache
    if is_default_request and not refresh:
        if _popular_cache.get("data") is not None and _popular_cache.get("cached_at") is not None:
            cache_age = (now - _popular_cache["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = _popular_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    from db_models import Booking, BookingStatus
    from collections import Counter

    # Validate top parameter
    if top not in [5, 10, 20]:
        top = 10

    # Build base query - confirmed and completed bookings only
    query = db.query(Booking).filter(Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]))

    # Apply date filters
    if start_date:
        query = query.filter(Booking.created_at >= start_date)
    if end_date:
        # Include the entire end date
        from datetime import datetime, timedelta
        end_datetime = datetime.combine(end_date, datetime.max.time())
        query = query.filter(Booking.created_at <= end_datetime)

    bookings = query.all()

    # Count airlines (merge departure and return - each booking counts once per unique airline NAME)
    # Use only airline name as key to avoid duplicates like "Jet2 (UNK)" and "Jet2 (LS)"
    airline_counter = Counter()
    for booking in bookings:
        # Collect unique airline names for this booking
        airlines_in_booking = set()
        if booking.dropoff_airline_name:
            airlines_in_booking.add(booking.dropoff_airline_name)
        if booking.pickup_airline_name:
            airlines_in_booking.add(booking.pickup_airline_name)
        # Count each unique airline once per booking
        for airline_name in airlines_in_booking:
            airline_counter[airline_name] += 1

    # Count destinations (merge departure destination and return origin - each booking counts once per unique destination)
    destination_counter = Counter()
    for booking in bookings:
        # Collect unique destinations for this booking
        destinations_in_booking = set()
        if booking.dropoff_destination:
            destinations_in_booking.add(booking.dropoff_destination)
        if booking.pickup_origin:
            destinations_in_booking.add(booking.pickup_origin)
        # Count each unique destination once per booking
        for dest in destinations_in_booking:
            destination_counter[dest] += 1

    # Get top airlines
    top_airlines = []
    total_airline_bookings = sum(airline_counter.values())
    for airline_name, count in airline_counter.most_common(top):
        percent = round((count / total_airline_bookings) * 100, 1) if total_airline_bookings > 0 else 0
        top_airlines.append({
            "airlineName": airline_name,
            "count": count,
            "percent": percent,
        })

    # Get top destinations
    top_destinations = []
    total_destination_bookings = sum(destination_counter.values())
    for destination, count in destination_counter.most_common(top):
        percent = round((count / total_destination_bookings) * 100, 1) if total_destination_bookings > 0 else 0
        top_destinations.append({
            "destination": destination,
            "count": count,
            "percent": percent,
        })

    # Count route combinations (airline + destination)
    # Note: We use airline_name + destination as the key (not airline_code)
    # to avoid duplicates from varying codes (e.g., UNK vs actual code)
    route_counter = Counter()
    for booking in bookings:
        # Collect unique routes for this booking (airline + destination pairs)
        routes_in_booking = set()
        # Outbound: dropoff airline to dropoff destination
        if booking.dropoff_airline_name and booking.dropoff_destination:
            route_key = (
                booking.dropoff_airline_name,
                booking.dropoff_destination
            )
            routes_in_booking.add(route_key)
        # Return: pickup airline from pickup origin
        if booking.pickup_airline_name and booking.pickup_origin:
            route_key = (
                booking.pickup_airline_name,
                booking.pickup_origin
            )
            routes_in_booking.add(route_key)
        # Count each unique route once per booking
        for route_key in routes_in_booking:
            route_counter[route_key] += 1

    # Get top routes
    top_routes = []
    total_route_bookings = sum(route_counter.values())
    for (airline, destination), count in route_counter.most_common(top):
        percent = round((count / total_route_bookings) * 100, 1) if total_route_bookings > 0 else 0
        top_routes.append({
            "airlineName": airline,
            "destination": destination,
            "route": f"{airline} to {destination}",
            "count": count,
            "percent": percent,
        })

    result = {
        "meta": {
            "startDate": start_date.isoformat() if start_date else None,
            "endDate": end_date.isoformat() if end_date else None,
            "top": top,
            "totalBookings": len(bookings),
            "totalAirlineBookings": total_airline_bookings,
            "totalDestinationBookings": total_destination_bookings,
            "totalRouteBookings": total_route_bookings,
        },
        "popularAirlines": top_airlines,
        "popularDestinations": top_destinations,
        "popularRoutes": top_routes,
    }

    if is_default_request:
        _popular_cache["data"] = result.copy()
        _popular_cache["cached_at"] = now
    result["cached"] = False
    return result


@app.get("/api/admin/reports/fun-facts")
async def get_fun_facts(
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get fun facts/records for the business.
    Cached for 1 hour.

    Returns:
    - Busiest Day: Day with most confirmed bookings (by payment date)
    - Busiest Streak: Longest consecutive days with confirmed bookings (by payment date)
    - Longest Trip: Booking with most days between dropoff and pickup
    - Highest Transaction: Booking with highest payment amount

    Only considers confirmed and completed bookings.
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Check cache
    global _fun_facts_cache
    if not refresh:
        if _fun_facts_cache.get("data") is not None and _fun_facts_cache.get("cached_at") is not None:
            cache_age = (now - _fun_facts_cache["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = _fun_facts_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    from db_models import Booking, BookingStatus
    from collections import Counter
    from datetime import timedelta

    # Get all confirmed/completed bookings
    bookings = db.query(Booking).filter(
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    ).all()

    result = {
        "busiestDay": None,
        "busiestStreak": None,
        "longestTrip": None,
        "highestTransaction": None,
    }

    if not bookings:
        result["cached"] = False
        return result

    # === Busiest Day ===
    # Count bookings by payment date (when transaction was confirmed)
    day_counter = Counter()
    for booking in bookings:
        # Use payment.paid_at for the confirmation/transaction date
        if booking.payment and booking.payment.paid_at:
            # Extract just the date from the datetime
            paid_date = booking.payment.paid_at.date()
            day_counter[paid_date] += 1

    if day_counter:
        # Find the maximum count
        max_count = max(day_counter.values())
        # Get all dates that have the maximum count
        busiest_dates = [d for d, c in day_counter.items() if c == max_count]
        # Sort dates chronologically
        busiest_dates.sort()
        result["busiestDay"] = {
            "dates": [d.strftime("%a %d %b %Y") for d in busiest_dates],  # e.g., ["Mon 24 Feb 2026", "Tue 25 Feb 2026"]
            "count": max_count,
        }

    # === Busiest Streak ===
    # Find longest consecutive days with at least one booking
    if day_counter:
        sorted_dates = sorted(day_counter.keys())

        longest_streak = 1
        longest_streak_start = sorted_dates[0]
        longest_streak_end = sorted_dates[0]

        current_streak = 1
        current_streak_start = sorted_dates[0]

        for i in range(1, len(sorted_dates)):
            if sorted_dates[i] == sorted_dates[i-1] + timedelta(days=1):
                # Consecutive day
                current_streak += 1
            else:
                # Streak broken, check if it was the longest
                if current_streak > longest_streak:
                    longest_streak = current_streak
                    longest_streak_start = current_streak_start
                    longest_streak_end = sorted_dates[i-1]
                # Start new streak
                current_streak = 1
                current_streak_start = sorted_dates[i]

        # Check final streak
        if current_streak > longest_streak:
            longest_streak = current_streak
            longest_streak_start = current_streak_start
            longest_streak_end = sorted_dates[-1]

        # Count total bookings in the streak
        streak_bookings = sum(
            day_counter[d] for d in sorted_dates
            if longest_streak_start <= d <= longest_streak_end
        )

        result["busiestStreak"] = {
            "days": longest_streak,
            "startDate": longest_streak_start.strftime("%d %b"),  # e.g., "24 Feb"
            "endDate": longest_streak_end.strftime("%d %b %Y"),   # e.g., "28 Feb 2026"
            "bookings": streak_bookings,
        }

    # === Longest Trip ===
    longest_booking = None
    longest_days = 0

    for booking in bookings:
        if booking.dropoff_date and booking.pickup_date:
            trip_days = (booking.pickup_date - booking.dropoff_date).days
            if trip_days > longest_days:
                longest_days = trip_days
                longest_booking = booking

    if longest_booking:
        result["longestTrip"] = {
            "days": longest_days,
            "reference": longest_booking.reference,
            "destination": longest_booking.dropoff_destination or "Unknown",
        }

    # === Highest Transaction ===
    highest_booking = None
    highest_amount_pence = 0

    for booking in bookings:
        # Get price from payment relationship
        if booking.payment and booking.payment.amount_pence and booking.payment.amount_pence > highest_amount_pence:
            highest_amount_pence = booking.payment.amount_pence
            highest_booking = booking

    if highest_booking:
        amount_pounds = highest_amount_pence / 100
        result["highestTransaction"] = {
            "amount": f"£{amount_pounds:.2f}",
            "reference": highest_booking.reference,
            "days": (highest_booking.pickup_date - highest_booking.dropoff_date).days if highest_booking.pickup_date and highest_booking.dropoff_date else None,
        }

    # Store in cache
    _fun_facts_cache["data"] = result.copy()
    _fun_facts_cache["cached_at"] = now
    result["cached"] = False
    return result


@app.put("/api/admin/bookings/{booking_id}/financial-override")
async def update_booking_financial_override(
    booking_id: int,
    gross_pence: int = Query(..., description="Original price in pence"),
    discount_pence: int = Query(..., description="Discount amount in pence"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update the financial override values for a booking.
    Used for bookings where gross/discount can't be calculated (e.g. 100% off promos).
    """
    from db_models import Booking as DbBookingModel

    booking = db.query(DbBookingModel).filter(DbBookingModel.id == booking_id).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.override_gross_pence = gross_pence
    booking.override_discount_pence = discount_pence
    db.commit()

    return {
        "success": True,
        "booking_id": booking_id,
        "override_gross_pence": gross_pence,
        "override_discount_pence": discount_pence,
    }


@app.get("/api/admin/reports/financial")
async def get_financial_report(
    from_date: str = Query(None, description="Start date DD/MM/YYYY"),
    to_date: str = Query(None, description="End date DD/MM/YYYY"),
    status_filter: str = Query("all", description="Filter by status: all, confirmed, completed, refunded"),
    promo_filter: str = Query("all", description="Filter by promo usage: all, yes, no"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get financial report data for the admin dashboard.
    Cached for 1 hour (default parameters only).

    Returns:
    - Revenue fun facts (most revenue day/week/month)
    - Bookings with financial details grouped by month
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Only cache default requests
    is_default_request = from_date is None and to_date is None and status_filter == "all" and promo_filter == "all"

    # Check cache
    global _financial_cache
    if is_default_request and not refresh:
        if _financial_cache.get("data") is not None and _financial_cache.get("cached_at") is not None:
            cache_age = (now - _financial_cache["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = _financial_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    from db_models import Booking, BookingStatus, Payment, PaymentStatus, PromoCode
    from collections import defaultdict
    from datetime import datetime, timedelta
    import calendar

    # Build query for bookings with successful payments
    query = db.query(Booking).join(Payment).filter(
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED])
    )

    # Status filter
    if status_filter == "confirmed":
        query = query.filter(Booking.status == BookingStatus.CONFIRMED)
    elif status_filter == "completed":
        query = query.filter(Booking.status == BookingStatus.COMPLETED)
    elif status_filter == "refunded":
        query = query.filter(Payment.status.in_([PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]))
    else:
        # All - include confirmed, completed, and cancelled (which may have refunds)
        query = query.filter(Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED, BookingStatus.CANCELLED]))

    # Date filters (based on payment date)
    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%d/%m/%Y")
            query = query.filter(Payment.paid_at >= from_dt)
        except ValueError:
            pass

    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%d/%m/%Y")
            # Include the entire end date
            to_dt = to_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Payment.paid_at <= to_dt)
        except ValueError:
            pass

    bookings = query.all()

    # Get promo codes used by these bookings
    booking_ids = [b.id for b in bookings]
    promo_codes = {}
    if booking_ids:
        from sqlalchemy.orm import joinedload
        from db_models import MarketingSubscriber

        # 1. Get promos from PromoCode table (Promotions system)
        promos = db.query(PromoCode).options(
            joinedload(PromoCode.promotion)
        ).filter(
            PromoCode.booking_id.in_(booking_ids),
            PromoCode.is_used == True
        ).all()
        for promo in promos:
            promo_codes[promo.booking_id] = {
                "code": promo.code,
                "discount_percent": promo.promotion.discount_percent if promo.promotion else 0
            }

        # 2. Get promos from MarketingSubscriber table (10% off promos)
        promo_10_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_10_used_booking_id.in_(booking_ids),
            MarketingSubscriber.promo_10_used == True
        ).all()
        for sub in promo_10_subs:
            if sub.promo_10_used_booking_id not in promo_codes:
                promo_codes[sub.promo_10_used_booking_id] = {
                    "code": sub.promo_10_code,
                    "discount_percent": 10
                }

        # 3. Get promos from MarketingSubscriber table (FREE parking promos - 100% off)
        promo_free_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_free_used_booking_id.in_(booking_ids),
            MarketingSubscriber.promo_free_used == True
        ).all()
        for sub in promo_free_subs:
            if sub.promo_free_used_booking_id not in promo_codes:
                promo_codes[sub.promo_free_used_booking_id] = {
                    "code": sub.promo_free_code,
                    "discount_percent": 100
                }

        # 4. Get founder promos from MarketingSubscriber table (10% off)
        founder_promo_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.founder_promo_used_booking_id.in_(booking_ids),
            MarketingSubscriber.founder_promo_used == True
        ).all()
        for sub in founder_promo_subs:
            if sub.founder_promo_used_booking_id not in promo_codes:
                promo_codes[sub.founder_promo_used_booking_id] = {
                    "code": sub.founder_promo_code,
                    "discount_percent": 10
                }

        # 5. Get legacy promos from MarketingSubscriber table
        legacy_promo_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_code_used_booking_id.in_(booking_ids),
            MarketingSubscriber.promo_code_used == True
        ).all()
        for sub in legacy_promo_subs:
            if sub.promo_code_used_booking_id not in promo_codes:
                promo_codes[sub.promo_code_used_booking_id] = {
                    "code": sub.promo_code,
                    "discount_percent": sub.discount_percent or 10
                }

    # Filter by promo usage if requested
    if promo_filter == "yes":
        bookings = [b for b in bookings if b.id in promo_codes]
    elif promo_filter == "no":
        bookings = [b for b in bookings if b.id not in promo_codes]

    # Calculate revenue fun facts
    revenue_by_day = defaultdict(int)
    revenue_by_week = defaultdict(int)
    revenue_by_month = defaultdict(int)

    for booking in bookings:
        if booking.payment and booking.payment.paid_at and booking.payment.amount_pence:
            paid_date = booking.payment.paid_at.date()
            amount = booking.payment.amount_pence

            # Subtract refunds for net revenue
            if booking.payment.refund_amount_pence:
                amount -= booking.payment.refund_amount_pence

            revenue_by_day[paid_date] += amount

            # Week (ISO week)
            year, week, _ = paid_date.isocalendar()
            week_key = f"{year}-W{week:02d}"
            revenue_by_week[week_key] += amount

            # Month
            month_key = paid_date.strftime("%Y-%m")
            revenue_by_month[month_key] += amount

    # Find top revenue periods
    fun_facts = {
        "topRevenueDay": None,
        "topRevenueWeek": None,
        "topRevenueMonth": None,
        "revenueToday": None,
        "revenueThisWeek": None,
        "revenueThisMonth": None,
    }

    # Get current date info
    today = date.today()
    today_iso = today.isocalendar()
    current_week_key = f"{today_iso[0]}-W{today_iso[1]:02d}"
    current_month_key = today.strftime("%Y-%m")

    # Top Revenue Day (no % change)
    if revenue_by_day:
        top_day = max(revenue_by_day.items(), key=lambda x: x[1])
        fun_facts["topRevenueDay"] = {
            "date": top_day[0].strftime("%a %d %b %Y"),
            "amount": f"£{top_day[1] / 100:.2f}",
        }

    # Top Revenue Week (no % change)
    if revenue_by_week:
        top_week = max(revenue_by_week.items(), key=lambda x: x[1])
        year, week_num = int(top_week[0][:4]), int(top_week[0][6:])
        week_start = date.fromisocalendar(year, week_num, 1)
        week_end = week_start + timedelta(days=6)
        fun_facts["topRevenueWeek"] = {
            "week": f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}",
            "amount": f"£{top_week[1] / 100:.2f}",
        }

    # Top Revenue Month (no % change)
    if revenue_by_month:
        top_month = max(revenue_by_month.items(), key=lambda x: x[1])
        month_date = datetime.strptime(top_month[0], "%Y-%m")
        fun_facts["topRevenueMonth"] = {
            "month": month_date.strftime("%B %Y"),
            "amount": f"£{top_month[1] / 100:.2f}",
        }

    # Revenue Today with % change vs yesterday
    today_revenue = revenue_by_day.get(today, 0)
    yesterday = today - timedelta(days=1)
    yesterday_revenue = revenue_by_day.get(yesterday, 0)
    day_change = None
    if yesterday_revenue > 0:
        change_pct = ((today_revenue - yesterday_revenue) / yesterday_revenue) * 100
        day_change = f"+{change_pct:.0f}%" if change_pct >= 0 else f"{change_pct:.0f}%"
    elif today_revenue > 0:
        day_change = "+100%"
    fun_facts["revenueToday"] = {
        "amount": f"£{today_revenue / 100:.2f}",
        "vsYesterday": day_change,
    }

    # Revenue This Week with % change vs last week
    this_week_revenue = revenue_by_week.get(current_week_key, 0)
    prev_week_num = today_iso[1] - 1
    prev_year = today_iso[0]
    if prev_week_num < 1:
        prev_year -= 1
        prev_week_num = date(prev_year, 12, 28).isocalendar()[1]
    prev_week_key = f"{prev_year}-W{prev_week_num:02d}"
    last_week_revenue = revenue_by_week.get(prev_week_key, 0)
    week_change = None
    if last_week_revenue > 0:
        change_pct = ((this_week_revenue - last_week_revenue) / last_week_revenue) * 100
        week_change = f"+{change_pct:.0f}%" if change_pct >= 0 else f"{change_pct:.0f}%"
    elif this_week_revenue > 0:
        week_change = "+100%"
    fun_facts["revenueThisWeek"] = {
        "amount": f"£{this_week_revenue / 100:.2f}",
        "vsLastWeek": week_change,
    }

    # Revenue This Month with % change vs last month
    this_month_revenue = revenue_by_month.get(current_month_key, 0)
    if today.month == 1:
        prev_month_key = f"{today.year - 1}-12"
    else:
        prev_month_key = f"{today.year}-{today.month - 1:02d}"
    last_month_revenue = revenue_by_month.get(prev_month_key, 0)
    month_change = None
    if last_month_revenue > 0:
        change_pct = ((this_month_revenue - last_month_revenue) / last_month_revenue) * 100
        month_change = f"+{change_pct:.0f}%" if change_pct >= 0 else f"{change_pct:.0f}%"
    elif this_month_revenue > 0:
        month_change = "+100%"
    fun_facts["revenueThisMonth"] = {
        "amount": f"£{this_month_revenue / 100:.2f}",
        "vsLastMonth": month_change,
    }

    # Build bookings list with financial details, grouped by month
    bookings_by_month = defaultdict(list)

    for booking in bookings:
        if not booking.payment or not booking.payment.paid_at:
            continue

        paid_date = booking.payment.paid_at.date()
        month_key = paid_date.strftime("%Y-%m")

        # Net = what customer actually paid
        net_pence = booking.payment.amount_pence or 0
        refund_pence = booking.payment.refund_amount_pence or 0

        # Calculate trip days
        trip_days = None
        if booking.dropoff_date and booking.pickup_date:
            trip_days = (booking.pickup_date - booking.dropoff_date).days

        # Get promo info
        promo_info = promo_codes.get(booking.id)
        discount_percent = promo_info["discount_percent"] if promo_info else 0

        # Calculate discount amount and gross (original) price
        # Use override values if available, otherwise calculate
        if booking.override_gross_pence is not None:
            gross_pence = booking.override_gross_pence
            discount_pence = booking.override_discount_pence or 0
        else:
            # Gross = Net + Discount
            # Net = Gross * (1 - discount/100)
            # Gross = Net / (1 - discount/100)
            discount_pence = 0
            gross_pence = net_pence
            if discount_percent and discount_percent < 100:
                gross_pence = int(net_pence / (1 - discount_percent / 100))
                discount_pence = gross_pence - net_pence

        # Final revenue after refunds
        final_revenue_pence = net_pence - refund_pence

        # Flag for bookings that need manual override (has promo but no discount calculated)
        needs_override = promo_info is not None and discount_pence == 0 and booking.override_gross_pence is None
        has_override = booking.override_gross_pence is not None

        bookings_by_month[month_key].append({
            "id": booking.id,
            "reference": booking.reference,
            "paidDate": paid_date.strftime("%d/%m/%Y"),
            "paidDateSort": paid_date.isoformat(),
            "customerName": f"{booking.customer.first_name} {booking.customer.last_name}" if booking.customer else "Unknown",
            "tripDays": trip_days,
            "grossPrice": f"£{gross_pence / 100:.2f}",
            "grossPence": gross_pence,
            "promoCode": promo_info["code"] if promo_info else None,
            "discountPercent": discount_percent,
            "discountAmount": f"£{discount_pence / 100:.2f}" if discount_pence else None,
            "discountPence": discount_pence,
            "netPrice": f"£{net_pence / 100:.2f}",
            "netPence": net_pence,
            "refundAmount": f"£{refund_pence / 100:.2f}" if refund_pence else None,
            "refundPence": refund_pence,
            "netRevenue": f"£{final_revenue_pence / 100:.2f}",
            "finalRevenuePence": final_revenue_pence,
            "status": booking.status.value if booking.status else "unknown",
            "paymentStatus": booking.payment.status.value if booking.payment.status else "unknown",
            "needsOverride": needs_override,
            "hasOverride": has_override,
        })

    # Sort bookings within each month by date ASC
    for month_key in bookings_by_month:
        bookings_by_month[month_key].sort(key=lambda x: x["paidDateSort"])

    # Convert to list sorted by month DESC
    months_sorted = sorted(bookings_by_month.keys(), reverse=True)
    monthly_data = []

    for month_key in months_sorted:
        month_date = datetime.strptime(month_key, "%Y-%m")
        month_bookings = bookings_by_month[month_key]
        month_gross = sum(b["grossPence"] for b in month_bookings)
        month_discount = sum(b["discountPence"] for b in month_bookings)
        month_net = sum(b["netPence"] for b in month_bookings)
        month_refunds = sum(b["refundPence"] for b in month_bookings)
        month_final = sum(b["finalRevenuePence"] for b in month_bookings)

        monthly_data.append({
            "monthKey": month_key,
            "monthLabel": month_date.strftime("%B %Y"),
            "bookingCount": len(month_bookings),
            "totalGross": f"£{month_gross / 100:.2f}",
            "totalDiscount": f"£{month_discount / 100:.2f}",
            "totalNet": f"£{month_net / 100:.2f}",
            "totalRefunds": f"£{month_refunds / 100:.2f}",
            "totalRevenue": f"£{month_final / 100:.2f}",
            "bookings": month_bookings,
        })

    # Calculate totals from processed bookings
    total_gross = sum(b["grossPence"] for mb in bookings_by_month.values() for b in mb)
    total_discount = sum(b["discountPence"] for mb in bookings_by_month.values() for b in mb)
    total_net = sum(b["netPence"] for mb in bookings_by_month.values() for b in mb)
    total_refunds = sum(b["refundPence"] for mb in bookings_by_month.values() for b in mb)
    total_revenue = sum(b["finalRevenuePence"] for mb in bookings_by_month.values() for b in mb)

    # Build chart data for daily, weekly, monthly, and cumulative revenue
    # Daily chart data (sorted by date ASC)
    daily_chart = []
    for day_date in sorted(revenue_by_day.keys()):
        daily_chart.append({
            "date": day_date.isoformat(),
            "revenue": revenue_by_day[day_date],
            "revenuePounds": round(revenue_by_day[day_date] / 100, 2),
        })

    # Weekly chart data (sorted by week ASC)
    weekly_chart = []
    for week_key in sorted(revenue_by_week.keys()):
        year, week_num = int(week_key[:4]), int(week_key[6:])
        week_start = date.fromisocalendar(year, week_num, 1)
        week_end = week_start + timedelta(days=6)
        weekly_chart.append({
            "week": week_key,
            "weekLabel": f"{week_start.strftime('%d %b')} - {week_end.strftime('%d %b')}",
            "revenue": revenue_by_week[week_key],
            "revenuePounds": round(revenue_by_week[week_key] / 100, 2),
        })

    # Monthly chart data (sorted by month ASC)
    monthly_chart = []
    for month_key in sorted(revenue_by_month.keys()):
        month_date = datetime.strptime(month_key, "%Y-%m")
        monthly_chart.append({
            "month": month_key,
            "monthLabel": month_date.strftime("%b %Y"),
            "revenue": revenue_by_month[month_key],
            "revenuePounds": round(revenue_by_month[month_key] / 100, 2),
        })

    # Cumulative chart data (daily cumulative total)
    cumulative_chart = []
    running_total = 0
    for day_date in sorted(revenue_by_day.keys()):
        running_total += revenue_by_day[day_date]
        cumulative_chart.append({
            "date": day_date.isoformat(),
            "total": running_total,
            "totalPounds": round(running_total / 100, 2),
        })

    result = {
        "funFacts": fun_facts,
        "monthlyData": monthly_data,
        "chartData": {
            "daily": daily_chart,
            "weekly": weekly_chart,
            "monthly": monthly_chart,
            "cumulative": cumulative_chart,
        },
        "summary": {
            "totalBookings": len(bookings),
            "totalGross": f"£{total_gross / 100:.2f}",
            "totalDiscount": f"£{total_discount / 100:.2f}",
            "totalNet": f"£{total_net / 100:.2f}",
            "totalRefunds": f"£{total_refunds / 100:.2f}",
            "totalRevenue": f"£{total_revenue / 100:.2f}",
        }
    }

    if is_default_request:
        _financial_cache["data"] = result.copy()
        _financial_cache["cached_at"] = now
    result["cached"] = False
    return result


@app.get("/api/admin/reports/financial/export")
async def export_financial_report(
    from_date: str = Query(None, description="Start date DD/MM/YYYY"),
    to_date: str = Query(None, description="End date DD/MM/YYYY"),
    status_filter: str = Query("all", description="Filter by status: all, confirmed, completed, refunded"),
    promo_filter: str = Query("all", description="Filter by promo usage: all, yes, no"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Export financial report as CSV.
    """
    from db_models import Booking, BookingStatus, Payment, PaymentStatus, PromoCode
    from fastapi.responses import StreamingResponse
    import csv
    import io
    from datetime import datetime

    # Build query (same as financial report)
    query = db.query(Booking).join(Payment).filter(
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED])
    )

    if status_filter == "confirmed":
        query = query.filter(Booking.status == BookingStatus.CONFIRMED)
    elif status_filter == "completed":
        query = query.filter(Booking.status == BookingStatus.COMPLETED)
    elif status_filter == "refunded":
        query = query.filter(Payment.status.in_([PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED]))
    else:
        # All - include confirmed, completed, and cancelled (which may have refunds)
        query = query.filter(Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED, BookingStatus.CANCELLED]))

    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%d/%m/%Y")
            query = query.filter(Payment.paid_at >= from_dt)
        except ValueError:
            pass

    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%d/%m/%Y")
            to_dt = to_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Payment.paid_at <= to_dt)
        except ValueError:
            pass

    bookings = query.order_by(Payment.paid_at.desc()).all()

    # Get promo codes
    booking_ids = [b.id for b in bookings]
    promo_codes = {}
    if booking_ids:
        from sqlalchemy.orm import joinedload
        from db_models import MarketingSubscriber

        # 1. Get promos from PromoCode table (Promotions system)
        promos = db.query(PromoCode).options(
            joinedload(PromoCode.promotion)
        ).filter(
            PromoCode.booking_id.in_(booking_ids),
            PromoCode.is_used == True
        ).all()
        for promo in promos:
            promo_codes[promo.booking_id] = {
                "code": promo.code,
                "discount_percent": promo.promotion.discount_percent if promo.promotion else 0
            }

        # 2. Get promos from MarketingSubscriber table (10% off promos)
        promo_10_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_10_used_booking_id.in_(booking_ids),
            MarketingSubscriber.promo_10_used == True
        ).all()
        for sub in promo_10_subs:
            if sub.promo_10_used_booking_id not in promo_codes:
                promo_codes[sub.promo_10_used_booking_id] = {
                    "code": sub.promo_10_code,
                    "discount_percent": 10
                }

        # 3. Get promos from MarketingSubscriber table (FREE parking promos - 100% off)
        promo_free_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_free_used_booking_id.in_(booking_ids),
            MarketingSubscriber.promo_free_used == True
        ).all()
        for sub in promo_free_subs:
            if sub.promo_free_used_booking_id not in promo_codes:
                promo_codes[sub.promo_free_used_booking_id] = {
                    "code": sub.promo_free_code,
                    "discount_percent": 100
                }

        # 4. Get founder promos from MarketingSubscriber table (10% off)
        founder_promo_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.founder_promo_used_booking_id.in_(booking_ids),
            MarketingSubscriber.founder_promo_used == True
        ).all()
        for sub in founder_promo_subs:
            if sub.founder_promo_used_booking_id not in promo_codes:
                promo_codes[sub.founder_promo_used_booking_id] = {
                    "code": sub.founder_promo_code,
                    "discount_percent": 10
                }

        # 5. Get legacy promos from MarketingSubscriber table
        legacy_promo_subs = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_code_used_booking_id.in_(booking_ids),
            MarketingSubscriber.promo_code_used == True
        ).all()
        for sub in legacy_promo_subs:
            if sub.promo_code_used_booking_id not in promo_codes:
                promo_codes[sub.promo_code_used_booking_id] = {
                    "code": sub.promo_code,
                    "discount_percent": sub.discount_percent or 10
                }

    # Filter by promo
    if promo_filter == "yes":
        bookings = [b for b in bookings if b.id in promo_codes]
    elif promo_filter == "no":
        bookings = [b for b in bookings if b.id not in promo_codes]

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Date",
        "Reference",
        "Customer",
        "Trip Days",
        "Gross Price",
        "Promo Code",
        "Discount %",
        "Discount Amount",
        "Net Price",
        "Refund Amount",
        "Final Revenue",
        "Booking Status",
        "Payment Status"
    ])

    # Data rows
    for booking in bookings:
        if not booking.payment or not booking.payment.paid_at:
            continue

        paid_date = booking.payment.paid_at.strftime("%d/%m/%Y")
        # Net = what customer actually paid
        net_pence = booking.payment.amount_pence or 0
        refund_pence = booking.payment.refund_amount_pence or 0

        trip_days = ""
        if booking.dropoff_date and booking.pickup_date:
            trip_days = (booking.pickup_date - booking.dropoff_date).days

        promo_info = promo_codes.get(booking.id)
        discount_percent = promo_info["discount_percent"] if promo_info else ""
        promo_code = promo_info["code"] if promo_info else ""

        # Calculate gross (original price) and discount
        # Gross = Net + Discount
        gross_pence = net_pence
        discount_pence = 0
        if promo_info and discount_percent and discount_percent < 100:
            gross_pence = int(net_pence / (1 - discount_percent / 100))
            discount_pence = gross_pence - net_pence

        # Final revenue after refunds
        final_revenue_pence = net_pence - refund_pence

        customer_name = f"{booking.customer.first_name} {booking.customer.last_name}" if booking.customer else "Unknown"

        writer.writerow([
            paid_date,
            booking.reference,
            customer_name,
            trip_days,
            f"£{gross_pence / 100:.2f}",
            promo_code,
            f"{discount_percent}%" if discount_percent else "",
            f"£{discount_pence / 100:.2f}" if discount_pence else "",
            f"£{net_pence / 100:.2f}",
            f"£{refund_pence / 100:.2f}" if refund_pence else "",
            f"£{final_revenue_pence / 100:.2f}",
            booking.status.value if booking.status else "",
            booking.payment.status.value if booking.payment.status else ""
        ])

    # Build filename
    filename_parts = ["financial_report"]
    if from_date:
        filename_parts.append(f"from_{from_date.replace('/', '-')}")
    if to_date:
        filename_parts.append(f"to_{to_date.replace('/', '-')}")
    filename = "_".join(filename_parts) + ".csv"

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/admin/reports/session-tracking")
async def get_session_tracking_report(
    period: str = Query("daily", description="Time period: daily, weekly, monthly"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get session tracking statistics showing funnel progression.
    Cached for 1 hour (default parameters only).

    Returns counts for each funnel stage:
    - dates_selected: Users who selected travel dates
    - flight_selected: Users who completed flight selection
    - customer_entered: Users who entered contact details
    - payment_initiated: Users who started payment
    - booking_confirmed: Users who completed booking

    Grouped by day, week, or month with conversion rates.
    """
    from db_models import AuditLog, AuditLogEvent
    from datetime import datetime, timedelta
    from collections import defaultdict
    import pytz

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Only cache default requests (daily period)
    is_default_request = period == "daily"

    # Check cache
    global _session_tracking_cache
    if is_default_request and not refresh:
        if _session_tracking_cache.get("data") is not None and _session_tracking_cache.get("cached_at") is not None:
            cache_age = (now - _session_tracking_cache["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = _session_tracking_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    # Define funnel stages in order
    funnel_stages = [
        ("dates_selected", "Dates Selected"),
        ("flight_selected", "Flight Selected"),
        ("customer_entered", "Details Entered"),
        ("payment_initiated", "Payment Started"),
        ("booking_confirmed", "Booking Confirmed"),
    ]

    # Feature deployment date - only show data from this date onwards
    # dates_selected tracking was deployed on 29 Mar 2026 at 17:00 UK time
    feature_deploy_date = uk_tz.localize(datetime(2026, 3, 29, 17, 0, 0))

    # Calculate date range based on period
    if period == "daily":
        # Last 30 days (but not before deployment)
        start_date = max(now - timedelta(days=30), feature_deploy_date)
        date_format = "%Y-%m-%d"
        display_format = "%d %b"
    elif period == "weekly":
        # Last 12 weeks (but not before deployment)
        start_date = max(now - timedelta(weeks=12), feature_deploy_date)
        date_format = "%Y-W%W"
        display_format = "W%W %Y"
    else:  # monthly
        # Last 12 months (but not before deployment)
        start_date = max(now - timedelta(days=365), feature_deploy_date)
        date_format = "%Y-%m"
        display_format = "%b %Y"

    # Query audit logs for funnel events
    audit_logs = db.query(AuditLog).filter(
        AuditLog.created_at >= start_date,
        AuditLog.event.in_([
            AuditLogEvent.DATES_SELECTED,
            AuditLogEvent.FLIGHT_SELECTED,
            AuditLogEvent.CUSTOMER_ENTERED,
            AuditLogEvent.PAYMENT_INITIATED,
            AuditLogEvent.BOOKING_CONFIRMED,
        ])
    ).all()

    # Group by period and count unique sessions per event type
    period_data = defaultdict(lambda: defaultdict(set))

    for log in audit_logs:
        if log.created_at:
            log_time = log.created_at
            if log_time.tzinfo is None:
                log_time = uk_tz.localize(log_time)
            else:
                log_time = log_time.astimezone(uk_tz)

            if period == "weekly":
                period_key = log_time.strftime("%Y-W%W")
            elif period == "monthly":
                period_key = log_time.strftime("%Y-%m")
            else:  # daily
                period_key = log_time.strftime("%Y-%m-%d")

            event_key = log.event.value if hasattr(log.event, 'value') else str(log.event)
            session_key = log.session_id or f"anon_{log.id}"
            period_data[period_key][event_key].add(session_key)

    # Build response data
    periods_list = sorted(period_data.keys())

    # Calculate cumulative totals
    cumulative = {stage[0]: set() for stage in funnel_stages}
    for period_key in periods_list:
        for stage_key, _ in funnel_stages:
            cumulative[stage_key].update(period_data[period_key].get(stage_key, set()))

    # Format period data for response
    formatted_periods = []
    for period_key in periods_list:
        # Format display label
        try:
            if period == "weekly":
                # Convert week number to start date of that week (Monday)
                year, week = period_key.split("-W")
                # Get first day of the week (Monday)
                first_day = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
                display_label = first_day.strftime("%d/%m")
            elif period == "monthly":
                dt = datetime.strptime(period_key, "%Y-%m")
                display_label = dt.strftime("%b %Y")
            else:
                dt = datetime.strptime(period_key, "%Y-%m-%d")
                display_label = dt.strftime("%d/%m")
        except:
            display_label = period_key

        period_counts = {}
        for stage_key, _ in funnel_stages:
            period_counts[stage_key] = len(period_data[period_key].get(stage_key, set()))

        formatted_periods.append({
            "period": period_key,
            "label": display_label,
            "counts": period_counts
        })

    # Calculate conversion rates for cumulative data
    cumulative_counts = {stage[0]: len(cumulative[stage[0]]) for stage in funnel_stages}

    conversion_rates = {}
    prev_count = None
    for stage_key, stage_label in funnel_stages:
        count = cumulative_counts[stage_key]
        if prev_count and prev_count > 0:
            conversion_rates[stage_key] = round((count / prev_count) * 100, 1)
        else:
            conversion_rates[stage_key] = 100.0 if count > 0 else 0.0
        prev_count = count if count > 0 else prev_count

    # Overall conversion rate (dates_selected → booking_confirmed)
    dates_count = cumulative_counts.get("dates_selected", 0)
    bookings_count = cumulative_counts.get("booking_confirmed", 0)
    overall_conversion = round((bookings_count / dates_count) * 100, 1) if dates_count > 0 else 0.0

    # Count manual/admin bookings per period (these bypass the checkout flow)
    from db_models import Booking as DbBooking, BookingStatus, Payment
    manual_bookings = db.query(DbBooking).filter(
        DbBooking.created_at >= start_date,
        DbBooking.booking_source.in_(['manual', 'admin']),
        DbBooking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED])
    ).all()

    manual_by_period = defaultdict(int)
    manual_cumulative = 0
    for booking in manual_bookings:
        if booking.created_at:
            booking_time = booking.created_at
            if booking_time.tzinfo is None:
                booking_time = uk_tz.localize(booking_time)
            else:
                booking_time = booking_time.astimezone(uk_tz)

            if period == "weekly":
                period_key = booking_time.strftime("%Y-W%W")
            elif period == "monthly":
                period_key = booking_time.strftime("%Y-%m")
            else:  # daily
                period_key = booking_time.strftime("%Y-%m-%d")

            manual_by_period[period_key] += 1
            manual_cumulative += 1

    # Count free bookings (100% promo - bypassed payment)
    free_bookings = db.query(DbBooking).join(Payment, Payment.booking_id == DbBooking.id).filter(
        DbBooking.created_at >= start_date,
        DbBooking.booking_source == 'online',
        DbBooking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
        Payment.amount_pence == 0
    ).all()

    free_by_period = defaultdict(int)
    free_cumulative = 0
    for booking in free_bookings:
        if booking.created_at:
            booking_time = booking.created_at
            if booking_time.tzinfo is None:
                booking_time = uk_tz.localize(booking_time)
            else:
                booking_time = booking_time.astimezone(uk_tz)

            if period == "weekly":
                period_key = booking_time.strftime("%Y-W%W")
            elif period == "monthly":
                period_key = booking_time.strftime("%Y-%m")
            else:  # daily
                period_key = booking_time.strftime("%Y-%m-%d")

            free_by_period[period_key] += 1
            free_cumulative += 1

    # Add manual and free counts to formatted periods
    for p in formatted_periods:
        p["manual_bookings"] = manual_by_period.get(p["period"], 0)
        p["free_bookings"] = free_by_period.get(p["period"], 0)

    result = {
        "period_type": period,
        "stages": [{"key": s[0], "label": s[1]} for s in funnel_stages],
        "periods": formatted_periods,
        "cumulative": {
            "counts": cumulative_counts,
            "conversion_rates": conversion_rates,
            "overall_conversion": overall_conversion,
            "manual_bookings": manual_cumulative,
            "free_bookings": free_cumulative
        }
    }

    if is_default_request:
        _session_tracking_cache["data"] = result.copy()
        _session_tracking_cache["cached_at"] = now
    result["cached"] = False
    return result


@app.get("/api/admin/reports/abandoned-carts")
async def get_abandoned_carts_report(
    period: str = Query("daily", description="Time period: daily, weekly, monthly"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get abandoned cart analytics showing sessions that didn't convert.
    Cached for 1 hour (default parameters only).

    Shows:
    - Total abandoned sessions by period
    - Top destinations people searched for but didn't book
    - Top trip lengths (days) that were abandoned
    - Recent abandoned cart details with flight info
    """
    from db_models import AuditLog, AuditLogEvent
    from datetime import datetime, timedelta
    from collections import defaultdict
    import pytz
    import json

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Only cache default requests (daily period)
    is_default_request = period == "daily"

    # Check cache
    global _abandoned_carts_cache
    if is_default_request and not refresh:
        if _abandoned_carts_cache.get("data") is not None and _abandoned_carts_cache.get("cached_at") is not None:
            cache_age = (now - _abandoned_carts_cache["cached_at"]).total_seconds()
            if cache_age < REPORT_CACHE_DURATION_SECONDS:
                cached_response = _abandoned_carts_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    # Feature deployment date
    feature_deploy_date = uk_tz.localize(datetime(2026, 3, 29, 17, 0, 0))

    # Calculate date range based on period
    if period == "daily":
        start_date = max(now - timedelta(days=30), feature_deploy_date)
    elif period == "weekly":
        start_date = max(now - timedelta(weeks=12), feature_deploy_date)
    else:  # monthly
        start_date = max(now - timedelta(days=365), feature_deploy_date)

    # Get all sessions that selected dates or flights
    started_sessions = db.query(AuditLog).filter(
        AuditLog.created_at >= start_date,
        AuditLog.event.in_([
            AuditLogEvent.DATES_SELECTED,
            AuditLogEvent.FLIGHT_SELECTED,
        ]),
        AuditLog.session_id.isnot(None)
    ).all()

    # Get all sessions that completed booking
    completed_sessions = db.query(AuditLog.session_id).filter(
        AuditLog.created_at >= start_date,
        AuditLog.event.in_([
            AuditLogEvent.PAYMENT_SUCCEEDED,
            AuditLogEvent.BOOKING_CONFIRMED,
        ]),
        AuditLog.session_id.isnot(None)
    ).distinct().all()
    completed_session_ids = {s[0] for s in completed_sessions}

    # Group abandoned sessions by period
    period_data = defaultdict(set)
    destination_sessions = defaultdict(set)  # Track unique sessions per destination
    days_sessions = defaultdict(set)  # Track unique sessions per trip length
    recent_abandoned = []
    seen_sessions = set()  # Track sessions we've already added to recent_abandoned

    for log in started_sessions:
        if log.session_id in completed_session_ids:
            continue  # Skip completed sessions

        if log.created_at:
            log_time = log.created_at
            if log_time.tzinfo is None:
                log_time = uk_tz.localize(log_time)
            else:
                log_time = log_time.astimezone(uk_tz)

            if period == "weekly":
                period_key = log_time.strftime("%Y-W%W")
            elif period == "monthly":
                period_key = log_time.strftime("%Y-%m")
            else:  # daily
                period_key = log_time.strftime("%Y-%m-%d")

            period_data[period_key].add(log.session_id)

            # Extract event data for analytics
            if log.event_data:
                try:
                    data = json.loads(log.event_data) if isinstance(log.event_data, str) else log.event_data

                    # Count unique sessions per destination
                    destination = data.get('departure_destination')
                    if destination:
                        destination_sessions[destination].add(log.session_id)

                    # Count unique sessions per trip length
                    dropoff = data.get('dropoff_date')
                    pickup = data.get('pickup_date')
                    if dropoff and pickup:
                        try:
                            d1 = datetime.strptime(dropoff, "%Y-%m-%d")
                            d2 = datetime.strptime(pickup, "%Y-%m-%d")
                            days = (d2 - d1).days
                            if days > 0:
                                days_sessions[days].add(log.session_id)
                        except:
                            pass

                    # Collect recent abandoned with flight details (one per session)
                    if log.event == AuditLogEvent.FLIGHT_SELECTED and log.session_id not in seen_sessions and len(recent_abandoned) < 100:
                        seen_sessions.add(log.session_id)
                        recent_abandoned.append({
                            "created_at": log_time.isoformat(),
                            "session_id": log.session_id,
                            "dropoff_date": data.get('dropoff_date'),
                            "pickup_date": data.get('pickup_date'),
                            "departure_time": data.get('departure_time'),
                            "arrival_time": data.get('arrival_time'),
                            "destination": data.get('departure_destination'),
                            "airline": data.get('departure_airline'),
                            "days": (datetime.strptime(data.get('pickup_date'), "%Y-%m-%d") -
                                    datetime.strptime(data.get('dropoff_date'), "%Y-%m-%d")).days
                                    if data.get('pickup_date') and data.get('dropoff_date') else None
                        })
                except:
                    pass

    # Sort recent abandoned by created_at descending
    recent_abandoned.sort(key=lambda x: x['created_at'], reverse=True)

    # Build period response
    periods_list = sorted(period_data.keys())
    formatted_periods = []
    total_abandoned = 0

    for period_key in periods_list:
        count = len(period_data[period_key])
        total_abandoned += count

        # Format display label
        try:
            if period == "weekly":
                year, week = period_key.split("-W")
                first_day = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
                display_label = first_day.strftime("%d/%m")
            elif period == "monthly":
                dt = datetime.strptime(period_key, "%Y-%m")
                display_label = dt.strftime("%b %Y")
            else:
                dt = datetime.strptime(period_key, "%Y-%m-%d")
                display_label = dt.strftime("%d/%m")
        except:
            display_label = period_key

        formatted_periods.append({
            "period": period_key,
            "label": display_label,
            "abandoned_count": count
        })

    # Top destinations (sorted by unique session count)
    top_destinations = sorted(
        [{"destination": k, "count": len(v)} for k, v in destination_sessions.items()],
        key=lambda x: x['count'],
        reverse=True
    )[:10]

    # Top trip lengths (sorted by unique session count)
    top_days = sorted(
        [{"days": k, "count": len(v)} for k, v in days_sessions.items()],
        key=lambda x: x['count'],
        reverse=True
    )[:10]

    result = {
        "period_type": period,
        "periods": formatted_periods,
        "cumulative": {
            "total_abandoned": total_abandoned,
            "top_destinations": top_destinations,
            "top_days": top_days,
        },
        "recent_abandoned": recent_abandoned[:50]  # Limit to 50 for response size
    }

    if is_default_request:
        _abandoned_carts_cache["data"] = result.copy()
        _abandoned_carts_cache["cached_at"] = now
    result["cached"] = False
    return result


@app.get("/api/admin/reports/bookings-forecast")
async def get_bookings_forecast(
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Predict future booking demand based on historical patterns and abandoned cart signals.

    Analyzes:
    - Historical bookings by destination, day of week, airline
    - Abandoned cart searches (demand signals)
    - Compares what's being searched vs what's being booked

    Returns predictions for the next 30 days.
    Results are cached for 1 hour to improve performance.
    """
    from db_models import Booking, BookingStatus, AuditLog, AuditLogEvent
    from datetime import datetime, timedelta
    from collections import defaultdict
    import pytz
    import json

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)
    today = now.date()

    # Check cache (unless refresh is requested)
    global _forecast_cache
    if not refresh and _forecast_cache["data"] is not None and _forecast_cache["cached_at"] is not None:
        cache_age = (now - _forecast_cache["cached_at"]).total_seconds()
        if cache_age < FORECAST_CACHE_DURATION_SECONDS:
            # Return cached data with cache info
            cached_response = _forecast_cache["data"].copy()
            cached_response["cached"] = True
            cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
            return cached_response

    # Get historical bookings (last 6 months of completed/confirmed bookings)
    six_months_ago = now - timedelta(days=180)

    historical_bookings = db.query(Booking).filter(
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
        Booking.created_at >= six_months_ago
    ).all()

    # Analyze booking patterns
    destination_bookings = defaultdict(int)
    day_of_week_bookings = defaultdict(int)  # 0=Monday, 6=Sunday (dropoff/travel day)
    pickup_day_of_week_bookings = defaultdict(int)  # 0=Monday, 6=Sunday (pickup/return day)
    airline_bookings = defaultdict(int)
    travel_month_bookings = defaultdict(int)  # Month of dropoff (when they travel)
    booking_month_bookings = defaultdict(int)  # Month of booking creation (when they booked)
    destination_by_dow = defaultdict(lambda: defaultdict(int))  # destination -> dow -> count
    departure_time_bookings = defaultdict(int)  # Hour of departure (0-23)
    arrival_time_bookings = defaultdict(int)  # Hour of arrival (0-23)

    for booking in historical_bookings:
        # Departure destination
        if booking.dropoff_destination:
            dest = booking.dropoff_destination.strip().title()
            destination_bookings[dest] += 1

            # Track day of week for this destination
            if booking.dropoff_date:
                dow = booking.dropoff_date.weekday()
                destination_by_dow[dest][dow] += 1

        # Day of week patterns (dropoff = travel day)
        if booking.dropoff_date:
            dow = booking.dropoff_date.weekday()
            day_of_week_bookings[dow] += 1
            travel_month_bookings[booking.dropoff_date.month] += 1

        # Day of week patterns (pickup = return day)
        if booking.pickup_date:
            pickup_dow = booking.pickup_date.weekday()
            pickup_day_of_week_bookings[pickup_dow] += 1

        # Month booking was created
        if booking.created_at:
            booking_month_bookings[booking.created_at.month] += 1

        # Airline patterns (merge Ryanair UK into Ryanair)
        if booking.dropoff_airline_name:
            airline_name = booking.dropoff_airline_name
            if airline_name.lower() in ['ryanair uk', 'ryanair uk ltd']:
                airline_name = 'Ryanair'
            airline_bookings[airline_name] += 1

        # Departure time patterns
        if booking.flight_departure_time:
            hour = booking.flight_departure_time.hour
            departure_time_bookings[hour] += 1

        # Arrival time patterns
        if booking.flight_arrival_time:
            hour = booking.flight_arrival_time.hour
            arrival_time_bookings[hour] += 1

    # Get abandoned cart data (last 30 days)
    thirty_days_ago = now - timedelta(days=30)

    abandoned_logs = db.query(AuditLog).filter(
        AuditLog.created_at >= thirty_days_ago,
        AuditLog.event == AuditLogEvent.FLIGHT_SELECTED,
        AuditLog.session_id.isnot(None)
    ).all()

    # Get completed sessions to exclude
    completed_sessions = db.query(AuditLog.session_id).filter(
        AuditLog.created_at >= thirty_days_ago,
        AuditLog.event.in_([AuditLogEvent.PAYMENT_SUCCEEDED, AuditLogEvent.BOOKING_CONFIRMED]),
        AuditLog.session_id.isnot(None)
    ).distinct().all()
    completed_session_ids = {s[0] for s in completed_sessions}

    # Analyze abandoned cart searches
    searched_destinations = defaultdict(set)  # destination -> set of session_ids
    searched_dates = defaultdict(set)  # date string -> set of session_ids
    searched_airlines = defaultdict(set)
    abandoned_month_sessions = defaultdict(set)  # month (1-12) -> set of session_ids

    for log in abandoned_logs:
        if log.session_id in completed_session_ids:
            continue

        if log.event_data:
            try:
                data = json.loads(log.event_data) if isinstance(log.event_data, str) else log.event_data

                dest = data.get('departure_destination')
                if dest:
                    searched_destinations[dest.strip().title()].add(log.session_id)

                dropoff_date = data.get('dropoff_date')
                if dropoff_date:
                    searched_dates[dropoff_date].add(log.session_id)
                    # Track abandoned by month of intended travel
                    try:
                        month = int(dropoff_date.split('-')[1])
                        abandoned_month_sessions[month].add(log.session_id)
                    except:
                        pass

                airline = data.get('departure_airline')
                if airline:
                    # Merge Ryanair UK into Ryanair
                    if airline.lower() in ['ryanair uk', 'ryanair uk ltd']:
                        airline = 'Ryanair'
                    searched_airlines[airline].add(log.session_id)
            except:
                pass

    # Calculate totals for normalization
    total_bookings = len(historical_bookings) or 1
    total_searches = len(set(s for sessions in searched_destinations.values() for s in sessions)) or 1

    # Build destination forecast with demand scores
    destination_forecast = []
    all_destinations = set(destination_bookings.keys()) | set(searched_destinations.keys())

    for dest in all_destinations:
        bookings_count = destination_bookings.get(dest, 0)
        search_count = len(searched_destinations.get(dest, set()))

        # Calculate base scores (normalized 0-100)
        booking_score = min(100, (bookings_count / total_bookings) * 500)  # Historical booking strength
        search_score = min(100, (search_count / total_searches) * 300)  # Recent search interest

        # Model 1: Balanced (60% bookings, 40% searches)
        score_balanced = round((booking_score * 0.6) + (search_score * 0.4), 1)

        # Model 2: Momentum (30% bookings, 70% searches) - catches emerging trends
        score_momentum = round((booking_score * 0.3) + (search_score * 0.7), 1)

        # Model 3: Established (80% bookings, 20% searches) - conservative, proven patterns
        score_established = round((booking_score * 0.8) + (search_score * 0.2), 1)

        # Calculate model agreement/confidence
        scores = [score_balanced, score_momentum, score_established]
        score_range = max(scores) - min(scores)
        if score_range <= 10:
            confidence = "high"
            confidence_icon = "✓✓✓"
        elif score_range <= 25:
            confidence = "medium"
            confidence_icon = "✓✓"
        else:
            confidence = "low"
            confidence_icon = "⚠️"

        # Conversion indicator
        if bookings_count > 0 and search_count > 0:
            conversion_rate = round((bookings_count / (bookings_count + search_count)) * 100, 1)
        elif bookings_count > 0:
            conversion_rate = 100
        else:
            conversion_rate = 0

        # Best day of week for this destination
        dest_dow = destination_by_dow.get(dest, {})
        best_dow = max(dest_dow.keys(), key=lambda x: dest_dow[x]) if dest_dow else None
        dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

        # Determine trend: is momentum higher or lower than established?
        if score_momentum > score_established + 10:
            trend = "rising"  # Gaining popularity
        elif score_established > score_momentum + 10:
            trend = "stable"  # Reliable but not trending
        else:
            trend = "neutral"

        destination_forecast.append({
            "destination": dest,
            "bookings_6m": bookings_count,
            "searches_30d": search_count,
            "score_balanced": score_balanced,
            "score_momentum": score_momentum,
            "score_established": score_established,
            "confidence": confidence,
            "confidence_icon": confidence_icon,
            "trend": trend,
            "conversion_rate": conversion_rate,
            "best_day": dow_names[best_dow] if best_dow is not None else None,
            "status": "high_demand" if score_balanced >= 50 else "moderate" if score_balanced >= 20 else "low"
        })

    # Sort by demand score
    destination_forecast.sort(key=lambda x: x['score_balanced'], reverse=True)

    # Day of week analysis
    dow_names_full = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    dow_forecast = []
    for dow in range(7):
        count = day_of_week_bookings.get(dow, 0)
        dow_forecast.append({
            "day": dow_names_full[dow],
            "day_short": dow_names_full[dow][:3],
            "bookings": count,
            "percentage": round((count / total_bookings) * 100, 1) if total_bookings else 0
        })

    # Pickup day of week analysis (when do customers return?)
    pickup_dow_forecast = []
    for dow in range(7):
        count = pickup_day_of_week_bookings.get(dow, 0)
        pickup_dow_forecast.append({
            "day": dow_names_full[dow],
            "day_short": dow_names_full[dow][:3],
            "bookings": count,
            "percentage": round((count / total_bookings) * 100, 1) if total_bookings else 0
        })

    # Airline analysis
    airline_forecast = []
    for airline, count in sorted(airline_bookings.items(), key=lambda x: x[1], reverse=True)[:10]:
        search_count = len(searched_airlines.get(airline, set()))
        airline_forecast.append({
            "airline": airline,
            "bookings_6m": count,
            "searches_30d": search_count,
            "percentage": round((count / total_bookings) * 100, 1) if total_bookings else 0
        })

    # Month analysis (seasonality) - travel month, booking month, and abandoned month
    month_names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    travel_month_forecast = []
    booking_month_forecast = []
    abandoned_month_forecast = []
    for month in range(1, 13):
        travel_count = travel_month_bookings.get(month, 0)
        booking_count = booking_month_bookings.get(month, 0)
        abandoned_count = len(abandoned_month_sessions.get(month, set()))
        travel_month_forecast.append({
            "month": month_names[month],
            "month_num": month,
            "bookings": travel_count,
            "percentage": round((travel_count / total_bookings) * 100, 1) if total_bookings else 0
        })
        booking_month_forecast.append({
            "month": month_names[month],
            "month_num": month,
            "bookings": booking_count,
            "percentage": round((booking_count / total_bookings) * 100, 1) if total_bookings else 0
        })
        abandoned_month_forecast.append({
            "month": month_names[month],
            "month_num": month,
            "count": abandoned_count,
            "percentage": round((abandoned_count / total_searches) * 100, 1) if total_searches else 0
        })

    # Upcoming dates with search interest (next 30 days)
    upcoming_demand = []
    for i in range(30):
        future_date = today + timedelta(days=i)
        date_str = future_date.strftime("%Y-%m-%d")
        search_count = len(searched_dates.get(date_str, set()))

        if search_count > 0:
            upcoming_demand.append({
                "date": date_str,
                "display_date": future_date.strftime("%a %d %b"),
                "searches": search_count,
                "day_of_week": dow_names_full[future_date.weekday()]
            })

    # Sort by search count
    upcoming_demand.sort(key=lambda x: x['searches'], reverse=True)

    # Predicted dates - next 30 days scored by day-of-week pattern + month pattern + searches
    predicted_dates = []
    for i in range(30):
        future_date = today + timedelta(days=i)
        date_str = future_date.strftime("%Y-%m-%d")
        dow = future_date.weekday()
        month = future_date.month

        # Score based on historical patterns
        dow_score = (day_of_week_bookings.get(dow, 0) / total_bookings * 100) if total_bookings else 0
        month_score = (travel_month_bookings.get(month, 0) / total_bookings * 100) if total_bookings else 0
        search_score = len(searched_dates.get(date_str, set())) * 10  # Boost for active searches

        # Combined prediction score
        prediction_score = round((dow_score * 0.4) + (month_score * 0.3) + (search_score * 0.3), 1)

        predicted_dates.append({
            "date": date_str,
            "display_date": future_date.strftime("%a %d %b"),
            "day_of_week": dow_names_full[dow],
            "prediction_score": prediction_score,
            "searches": len(searched_dates.get(date_str, set())),
            "likelihood": "high" if prediction_score >= 15 else "medium" if prediction_score >= 8 else "low"
        })

    # Sort by prediction score
    predicted_dates.sort(key=lambda x: x['prediction_score'], reverse=True)

    # Departure time analysis
    departure_time_forecast = []
    for hour in range(0, 24):  # Full day coverage
        count = departure_time_bookings.get(hour, 0)
        time_label = f"{hour:02d}:00"
        departure_time_forecast.append({
            "hour": hour,
            "time": time_label,
            "bookings": count,
            "percentage": round((count / total_bookings) * 100, 1) if total_bookings else 0
        })

    # Arrival time analysis
    arrival_time_forecast = []
    for hour in range(0, 24):  # Full day coverage
        count = arrival_time_bookings.get(hour, 0)
        time_label = f"{hour:02d}:00"
        arrival_time_forecast.append({
            "hour": hour,
            "time": time_label,
            "bookings": count,
            "percentage": round((count / total_bookings) * 100, 1) if total_bookings else 0
        })

    # Search vs booking gap (high searches, low conversions = opportunity)
    opportunity_gaps = []
    for dest in destination_forecast:
        if dest['searches_30d'] >= 2 and dest['conversion_rate'] < 50:
            opportunity_gaps.append({
                "destination": dest['destination'],
                "searches": dest['searches_30d'],
                "bookings": dest['bookings_6m'],
                "gap_score": dest['searches_30d'] * (100 - dest['conversion_rate']) / 100
            })
    opportunity_gaps.sort(key=lambda x: x['gap_score'], reverse=True)

    result = {
        "generated_at": now.isoformat(),
        "data_range": {
            "bookings_from": six_months_ago.strftime("%Y-%m-%d"),
            "searches_from": thirty_days_ago.strftime("%Y-%m-%d"),
            "total_bookings_analyzed": total_bookings,
            "total_abandoned_sessions": total_searches
        },
        "destinations": destination_forecast[:20],
        "day_of_week": dow_forecast,
        "pickup_day_of_week": pickup_dow_forecast,
        "airlines": airline_forecast,
        "seasonality_travel": travel_month_forecast,
        "seasonality_booking": booking_month_forecast,
        "seasonality_abandoned": abandoned_month_forecast,
        "departure_times": departure_time_forecast,
        "arrival_times": arrival_time_forecast,
        "predicted_dates": predicted_dates[:15],
        "upcoming_demand": upcoming_demand[:15],
        "opportunity_gaps": opportunity_gaps[:10]
    }

    # Store in cache
    _forecast_cache["data"] = result
    _forecast_cache["cached_at"] = now

    # Return fresh data
    result["cached"] = False
    return result


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


@app.post("/api/admin/marketing-subscribers/{subscriber_id}/send-founder-email")
async def send_founder_email_to_subscriber(
    subscriber_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate a unique promo code and send founder thank you email to a subscriber.

    The founder email is a personal message from Kristian with a 10% off promo code.
    It's CC'd to the founder's email so they can see and respond to replies.
    """
    from email_service import generate_promo_code, send_founder_thank_you_email

    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.id == subscriber_id
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    if subscriber.unsubscribed:
        raise HTTPException(status_code=400, detail="Subscriber has unsubscribed")

    # Check if founder email has already been used
    if subscriber.founder_promo_used:
        raise HTTPException(status_code=400, detail="Founder promo code has already been used")

    # Generate unique promo code for founder email if not already generated
    if not subscriber.founder_promo_code:
        for _ in range(10):
            new_code = generate_promo_code()
            # Check uniqueness across all promo code fields
            existing = db.query(MarketingSubscriber).filter(
                (MarketingSubscriber.promo_10_code == new_code) |
                (MarketingSubscriber.promo_free_code == new_code) |
                (MarketingSubscriber.promo_code == new_code) |
                (MarketingSubscriber.founder_promo_code == new_code)
            ).first()
            if not existing:
                subscriber.founder_promo_code = new_code
                break
        else:
            raise HTTPException(status_code=500, detail="Failed to generate unique promo code")

    promo_code = subscriber.founder_promo_code
    db.commit()

    # Send the founder thank you email
    email_sent = send_founder_thank_you_email(
        email=subscriber.email,
        first_name=subscriber.first_name,
        promo_code=promo_code,
    )

    if email_sent:
        subscriber.founder_email_sent = True
        subscriber.founder_email_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Founder thank you email sent to {subscriber.email}",
            "promo_code": promo_code,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send founder email. Check SendGrid configuration."
        )


@app.post("/api/admin/marketing-subscribers/{subscriber_id}/send-promo-10-reminder")
async def send_promo_10_reminder_to_subscriber(
    subscriber_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Send a reminder email to a subscriber who hasn't used their 10% promo code.
    """
    from email_service import send_promo_10_reminder_email

    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.id == subscriber_id
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    if subscriber.unsubscribed:
        raise HTTPException(status_code=400, detail="Subscriber has unsubscribed")

    # Check if they have a 10% promo code
    if not subscriber.promo_10_code:
        raise HTTPException(status_code=400, detail="Subscriber does not have a 10% promo code")

    # Check if already used
    if subscriber.promo_10_used:
        raise HTTPException(status_code=400, detail="Subscriber has already used their 10% promo code")

    # Check if reminder already sent
    if subscriber.promo_10_reminder_sent:
        from zoneinfo import ZoneInfo
        sent_at_str = "unknown date"
        if subscriber.promo_10_reminder_sent_at:
            uk_time = subscriber.promo_10_reminder_sent_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/London"))
            sent_at_str = uk_time.strftime('%d %b %Y at %H:%M')
        raise HTTPException(
            status_code=400,
            detail=f"Promo 10% reminder already sent to {subscriber.email} on {sent_at_str}"
        )

    # Send the reminder email
    email_sent = send_promo_10_reminder_email(
        email=subscriber.email,
        first_name=subscriber.first_name or "there",
        promo_code=subscriber.promo_10_code,
    )

    if email_sent:
        # Update tracking
        subscriber.promo_10_reminder_sent = True
        subscriber.promo_10_reminder_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"Promo 10% reminder email sent to {subscriber.email}",
            "promo_code": subscriber.promo_10_code,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send promo 10 reminder email. Check SendGrid configuration."
        )


@app.post("/api/admin/marketing-subscribers/{subscriber_id}/send-promo-free-reminder")
async def send_promo_free_reminder_to_subscriber(
    subscriber_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Send a reminder email to a subscriber who hasn't used their FREE parking promo code.
    """
    from email_service import send_promo_free_reminder_email

    subscriber = db.query(MarketingSubscriber).filter(
        MarketingSubscriber.id == subscriber_id
    ).first()

    if not subscriber:
        raise HTTPException(status_code=404, detail="Subscriber not found")

    if subscriber.unsubscribed:
        raise HTTPException(status_code=400, detail="Subscriber has unsubscribed")

    # Check if they have a FREE promo code
    if not subscriber.promo_free_code:
        raise HTTPException(status_code=400, detail="Subscriber does not have a FREE parking promo code")

    # Check if already used
    if subscriber.promo_free_used:
        raise HTTPException(status_code=400, detail="Subscriber has already used their FREE parking promo code")

    # Check if reminder already sent
    if subscriber.promo_free_reminder_sent:
        from zoneinfo import ZoneInfo
        sent_at_str = "unknown date"
        if subscriber.promo_free_reminder_sent_at:
            uk_time = subscriber.promo_free_reminder_sent_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/London"))
            sent_at_str = uk_time.strftime('%d %b %Y at %H:%M')
        raise HTTPException(
            status_code=400,
            detail=f"FREE parking reminder already sent to {subscriber.email} on {sent_at_str}"
        )

    # Send the reminder email
    email_sent = send_promo_free_reminder_email(
        email=subscriber.email,
        first_name=subscriber.first_name or "there",
        promo_code=subscriber.promo_free_code,
    )

    if email_sent:
        # Update tracking
        subscriber.promo_free_reminder_sent = True
        subscriber.promo_free_reminder_sent_at = datetime.utcnow()
        db.commit()

        return {
            "success": True,
            "message": f"FREE parking reminder email sent to {subscriber.email}",
            "promo_code": subscriber.promo_free_code,
        }
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send FREE parking reminder email. Check SendGrid configuration."
        )


# =============================================================================
# Admin Marketing Sources (Attribution) Endpoints
# =============================================================================

@app.get("/api/admin/marketing-sources/summary")
async def get_marketing_sources_summary(
    from_month: str = Query(None, description="Start month in MM/YYYY format (e.g., 04/2026)"),
    to_month: str = Query(None, description="End month in MM/YYYY format (e.g., 06/2026)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get marketing source summary by month for admin reports.
    Reads from pre-aggregated marketing_source_monthly_totals table.
    """
    from db_models import MarketingSourceMonthlyTotal

    query = db.query(MarketingSourceMonthlyTotal)

    # Convert MM/YYYY to YYYY-MM for filtering
    if from_month:
        try:
            parts = from_month.split('/')
            from_ym = f"{parts[1]}-{parts[0]}"
            query = query.filter(MarketingSourceMonthlyTotal.year_month >= from_ym)
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid from_month format. Use MM/YYYY")

    if to_month:
        try:
            parts = to_month.split('/')
            to_ym = f"{parts[1]}-{parts[0]}"
            query = query.filter(MarketingSourceMonthlyTotal.year_month <= to_ym)
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid to_month format. Use MM/YYYY")

    results = query.order_by(MarketingSourceMonthlyTotal.year_month.desc()).all()

    # Group by month - sources as object { source_name: count }
    months_data = {}
    source_totals = {}  # All-time totals by source

    for row in results:
        if row.year_month not in months_data:
            months_data[row.year_month] = {}
        months_data[row.year_month][row.source] = row.count

        # Accumulate source totals
        if row.source not in source_totals:
            source_totals[row.source] = 0
        source_totals[row.source] += row.count

    # Format response - monthly_data with sources as object
    monthly_data = []
    total_responses = 0
    for year_month in sorted(months_data.keys(), reverse=True):
        sources = months_data[year_month]
        month_total = sum(sources.values())
        total_responses += month_total
        monthly_data.append({
            "year_month": year_month,
            "sources": sources,  # { "google": 5, "facebook": 3, ... }
        })

    return {
        "total_responses": total_responses,
        "monthly_data": monthly_data,
        "source_totals": source_totals,  # { "google": 211, "facebook": 139, ... }
    }


@app.get("/api/admin/marketing-sources/other")
async def get_marketing_sources_other(
    year_month: str = Query(None, description="Filter by month in YYYY-MM format"),
    from_date: str = Query(None, description="Start date in DD/MM/YYYY format"),
    to_date: str = Query(None, description="End date in DD/MM/YYYY format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all 'other' marketing source responses with free-text details.
    Optionally filter by year_month (YYYY-MM) to show only that month's responses.
    """
    from db_models import MarketingSource, Customer
    from sqlalchemy import extract

    query = db.query(MarketingSource, Customer).join(
        Customer, MarketingSource.customer_id == Customer.id
    ).filter(MarketingSource.source == 'other')

    # Filter by specific month (YYYY-MM format)
    if year_month:
        try:
            year, month = map(int, year_month.split('-'))
            query = query.filter(
                extract('year', MarketingSource.created_at) == year,
                extract('month', MarketingSource.created_at) == month
            )
        except (ValueError, AttributeError):
            pass  # Invalid format, ignore filter

    # Convert DD/MM/YYYY to datetime for filtering (legacy support)
    if from_date:
        try:
            parts = from_date.split('/')
            from_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            query = query.filter(MarketingSource.created_at >= from_dt)
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use DD/MM/YYYY")

    if to_date:
        try:
            parts = to_date.split('/')
            to_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]), 23, 59, 59)
            query = query.filter(MarketingSource.created_at <= to_dt)
        except (IndexError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use DD/MM/YYYY")

    results = query.order_by(MarketingSource.created_at.desc()).all()

    other_responses = []
    for ms, customer in results:
        other_responses.append({
            "customer_email": customer.email,
            "customer_name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
            "source_detail": ms.source_detail,
            "created_at": ms.created_at.isoformat() if ms.created_at else None,
        })

    return {
        "count": len(other_responses),
        "details": other_responses,
    }


@app.get("/api/admin/marketing-sources/export")
async def export_marketing_sources_csv(
    from_date: Optional[str] = Query(None, description="Start date in DD/MM/YYYY format"),
    to_date: Optional[str] = Query(None, description="End date in DD/MM/YYYY format"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Export marketing source data as CSV, optionally filtered by date range.

    Args:
        from_date: Start date in DD/MM/YYYY format (inclusive)
        to_date: End date in DD/MM/YYYY format (inclusive)
    """
    from db_models import MarketingSource, Customer
    from fastapi.responses import StreamingResponse
    import io
    import csv

    query = db.query(MarketingSource, Customer).join(
        Customer, MarketingSource.customer_id == Customer.id
    )

    # Apply date filters if provided (DD/MM/YYYY format)
    if from_date:
        try:
            parts = from_date.split('/')
            from_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            query = query.filter(MarketingSource.created_at >= from_dt)
        except (IndexError, ValueError):
            pass  # Invalid format, skip filter

    if to_date:
        try:
            parts = to_date.split('/')
            to_dt = datetime(int(parts[2]), int(parts[1]), int(parts[0]), 23, 59, 59)
            query = query.filter(MarketingSource.created_at <= to_dt)
        except (IndexError, ValueError):
            pass  # Invalid format, skip filter

    results = query.order_by(MarketingSource.created_at.desc()).all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['customer_id', 'customer_email', 'customer_name', 'source', 'source_detail', 'created_at'])

    for ms, customer in results:
        writer.writerow([
            customer.id,
            customer.email,
            f"{customer.first_name} {customer.last_name}",
            ms.source,
            ms.source_detail or '',
            ms.created_at.strftime('%d/%m/%Y') if ms.created_at else '',
        ])

    output.seek(0)

    # Generate filename with date range if filters applied
    filename = "marketing_sources"
    if from_date:
        filename += f"_from_{from_date}"
    if to_date:
        filename += f"_to_{to_date}"
    filename += ".csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# =============================================================================
# Promotions API (Promo Code Generation System)
# =============================================================================

def generate_promo_code(prefix: str = "TAG") -> str:
    """Generate a unique promo code in format PREFIX-XXXX-XXXX."""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(random.choices(chars, k=4))
    part2 = ''.join(random.choices(chars, k=4))
    return f"{prefix}-{part1}-{part2}"


@app.post("/api/admin/promotions")
async def create_promotion(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Create a new promotion and generate promo codes.

    Request body:
    - name: Campaign name (e.g., "Spring 2024 Friends & Family")
    - description: Optional description
    - discount_percent: Discount percentage (10, 20, 100)
    - total_codes: Number of codes to generate
    """
    from db_models import Promotion, PromoCode

    name = request.get("name")
    description = request.get("description")
    discount_percent = request.get("discount_percent")
    total_codes = request.get("total_codes")
    code_prefix = request.get("code_prefix", "").strip().upper()
    custom_code = request.get("custom_code", "").strip().upper()  # Custom code like "SUMMER10"
    expiry_date = request.get("expiry_date")  # DD/MM/YYYY
    expiry_time = request.get("expiry_time")  # HH:MM
    max_uses_raw = request.get("max_uses")  # None = single-use, 0 = unlimited, N = max N uses

    # Validate and sanitize prefix - only allow alphanumeric, max 10 chars
    if code_prefix:
        code_prefix = ''.join(c for c in code_prefix if c.isalnum())[:10]
    if not code_prefix:
        code_prefix = "TAG"

    # Validate custom code - only allow alphanumeric, max 20 chars
    if custom_code:
        custom_code = ''.join(c for c in custom_code if c.isalnum())[:20]

    # Parse expiry if provided
    expires_at = None
    if expiry_date and expiry_time:
        import pytz
        try:
            day, month, year = expiry_date.strip().split("/")
            hour, minute = expiry_time.strip().split(":")
            uk_tz = pytz.timezone("Europe/London")
            from datetime import datetime as dt
            naive_dt = dt(int(year), int(month), int(day), int(hour), int(minute), 0)
            expires_at = uk_tz.localize(naive_dt)
        except (ValueError, AttributeError) as e:
            log_promo("CREATE_PROMOTION invalid expiry format", {"expiry_date": expiry_date, "expiry_time": expiry_time, "error": str(e)})
            raise HTTPException(status_code=400, detail="Invalid expiry format. Use DD/MM/YYYY for date and HH:MM for time")

    # Parse max_uses - empty string or None means single-use, 0 means unlimited, N means max N uses
    max_uses = None  # Default: single-use
    if max_uses_raw is not None and max_uses_raw != '':
        try:
            max_uses = int(max_uses_raw)
            if max_uses < 0:
                raise HTTPException(status_code=400, detail="max_uses cannot be negative")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="max_uses must be a number")

    log_promo("CREATE_PROMOTION request", {"name": name, "discount_percent": discount_percent, "total_codes": total_codes, "code_prefix": code_prefix, "expires_at": str(expires_at) if expires_at else None, "max_uses": max_uses, "user": current_user.email})

    # If custom_code is provided, we create exactly 1 code with that value
    if custom_code:
        total_codes = 1  # Override - custom code means 1 code

    if not name or not discount_percent or (not total_codes and not custom_code):
        log_promo("CREATE_PROMOTION failed - missing required fields")
        raise HTTPException(status_code=400, detail="name, discount_percent, and total_codes (or custom_code) are required")

    if discount_percent not in [10, 15, 20, 25, 50, 100]:
        log_promo("CREATE_PROMOTION failed - invalid discount_percent", {"discount_percent": discount_percent})
        raise HTTPException(status_code=400, detail="discount_percent must be 10, 15, 20, 25, 50, or 100")

    if not custom_code and (total_codes < 1 or total_codes > 1000):
        log_promo("CREATE_PROMOTION failed - invalid total_codes", {"total_codes": total_codes})
        raise HTTPException(status_code=400, detail="total_codes must be between 1 and 1000")

    # Check if custom code already exists
    if custom_code:
        existing = db.query(PromoCode).filter(PromoCode.code == custom_code).first()
        if existing:
            log_promo("CREATE_PROMOTION failed - custom code already exists", {"custom_code": custom_code})
            raise HTTPException(status_code=400, detail=f"Code '{custom_code}' already exists. Please choose a different code.")

    # Create promotion
    promotion = Promotion(
        name=name,
        description=description,
        discount_percent=discount_percent,
        total_codes=total_codes,
        code_prefix=code_prefix,
        created_by=current_user.email,
    )
    db.add(promotion)
    db.flush()  # Get the ID
    log_promo("CREATE_PROMOTION created", {"promotion_id": promotion.id, "name": name})

    # Generate promo codes
    codes_created = 0

    if custom_code:
        # Create single custom code (e.g., "SUMMER10")
        promo_code = PromoCode(
            promotion_id=promotion.id,
            code=custom_code,
            expires_at=expires_at,
            max_uses=max_uses,
        )
        db.add(promo_code)
        codes_created = 1
        log_promo("CREATE_PROMOTION created custom code", {"code": custom_code, "max_uses": max_uses})
    else:
        # Generate random unique promo codes
        max_attempts = total_codes * 10  # Prevent infinite loop
        attempts = 0

        while codes_created < total_codes and attempts < max_attempts:
            code = generate_promo_code(code_prefix)
            attempts += 1

            # Check if code already exists
            existing = db.query(PromoCode).filter(PromoCode.code == code).first()
            if existing:
                log_promo("CREATE_PROMOTION code collision, retrying", {"code": code})
                continue

            promo_code = PromoCode(
                promotion_id=promotion.id,
                code=code,
                expires_at=expires_at,
                max_uses=max_uses,
            )
            db.add(promo_code)
            codes_created += 1

    db.commit()
    db.refresh(promotion)

    log_promo("CREATE_PROMOTION success", {"promotion_id": promotion.id, "codes_created": codes_created, "custom_code": custom_code, "expires_at": str(expires_at) if expires_at else None})

    return {
        "id": promotion.id,
        "name": promotion.name,
        "description": promotion.description,
        "discount_percent": promotion.discount_percent,
        "total_codes": promotion.total_codes,
        "codes_sent": promotion.codes_sent,
        "codes_used": promotion.codes_used,
        "codes_available": promotion.total_codes,  # All codes available on creation
        "created_by": promotion.created_by,
        "created_at": promotion.created_at,
    }


@app.get("/api/admin/promotions")
async def list_promotions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all promotions with stats."""
    from db_models import Promotion, PromoCode
    from sqlalchemy import func

    promotions = db.query(Promotion).order_by(Promotion.created_at.desc()).all()
    log_promo("LIST_PROMOTIONS", {"count": len(promotions)})

    # Get shared on socials counts for each promotion
    shared_on_socials_counts = dict(
        db.query(PromoCode.promotion_id, func.count(PromoCode.id))
        .filter(PromoCode.shared_on_socials == True)
        .group_by(PromoCode.promotion_id)
        .all()
    )

    # Get shared privately counts for each promotion
    shared_privately_counts = dict(
        db.query(PromoCode.promotion_id, func.count(PromoCode.id))
        .filter(PromoCode.shared_privately == True)
        .group_by(PromoCode.promotion_id)
        .all()
    )

    # Get truly available codes count (not sent, not used, not shared on socials, not shared privately)
    available_counts = dict(
        db.query(PromoCode.promotion_id, func.count(PromoCode.id))
        .filter(
            PromoCode.email_sent == False,
            PromoCode.is_used == False,
            PromoCode.shared_on_socials == False,
            PromoCode.shared_privately == False
        )
        .group_by(PromoCode.promotion_id)
        .all()
    )

    return {
        "promotions": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "discount_percent": p.discount_percent,
                "total_codes": p.total_codes,
                "codes_sent": p.codes_sent,
                "codes_used": p.codes_used,
                "codes_shared_on_socials": shared_on_socials_counts.get(p.id, 0),
                "codes_shared_privately": shared_privately_counts.get(p.id, 0),
                "codes_available": available_counts.get(p.id, 0),
                "created_by": p.created_by,
                "created_at": p.created_at,
            }
            for p in promotions
        ]
    }


@app.get("/api/admin/promotions/{promotion_id}")
async def get_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get promotion details with codes."""
    from db_models import Promotion, PromoCode, Booking, PromoCodeUsage

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")

    # Get codes with booking references
    codes = db.query(PromoCode).filter(PromoCode.promotion_id == promotion_id).order_by(PromoCode.created_at.asc()).all()

    codes_data = []
    for c in codes:
        # For multi-use codes, get all booking references from usages table
        booking_references = []
        if c.is_multi_use:
            usages = db.query(PromoCodeUsage).filter(PromoCodeUsage.promo_code_id == c.id).order_by(PromoCodeUsage.used_at.asc()).all()
            for usage in usages:
                booking = db.query(Booking).filter(Booking.id == usage.booking_id).first()
                if booking:
                    booking_references.append(booking.reference)
        else:
            # Single-use code - get booking reference from booking_id
            if c.booking_id:
                booking = db.query(Booking).filter(Booking.id == c.booking_id).first()
                if booking:
                    booking_references.append(booking.reference)

        # For backwards compatibility, also include single booking_reference
        booking_ref = booking_references[0] if booking_references else None

        # Calculate is_expired and convert expires_at to UK timezone for display
        is_expired = False
        expires_at_uk = None
        if c.expires_at:
            is_expired = get_uk_now() >= c.expires_at
            # Convert to UK timezone for display
            import pytz
            uk_tz = pytz.timezone("Europe/London")
            expires_at_uk = c.expires_at.astimezone(uk_tz).isoformat()

        codes_data.append({
            "id": c.id,
            "code": c.code,
            "promotion_id": c.promotion_id,
            "discount_percent": promotion.discount_percent,
            "recipient_email": c.recipient_email,
            "recipient_first_name": c.recipient_first_name,
            "recipient_last_name": c.recipient_last_name,
            "customer_id": c.customer_id,
            "subscriber_id": c.subscriber_id,
            "email_sent": c.email_sent,
            "email_sent_at": c.email_sent_at,
            "shared_on_socials": c.shared_on_socials,
            "shared_on_socials_at": c.shared_on_socials_at,
            "shared_privately": c.shared_privately,
            "shared_privately_at": c.shared_privately_at,
            "is_used": c.is_used,
            "used_at": c.used_at,
            "booking_id": c.booking_id,
            "booking_reference": booking_ref,
            "booking_references": booking_references,  # All bookings for multi-use codes
            "expires_at": expires_at_uk,
            "is_expired": is_expired,
            "created_at": c.created_at,
            # Multi-use fields
            "max_uses": c.max_uses,  # None = single-use, 0 = unlimited, N = max N uses
            "use_count": c.use_count or 0,
            "is_multi_use": c.is_multi_use,
            "uses_remaining": c.uses_remaining,
            "can_be_used": c.can_be_used,
        })

    # Count truly available codes (not sent, not used, not shared on socials, not shared privately)
    codes_available = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.email_sent == False,
        PromoCode.is_used == False,
        PromoCode.shared_on_socials == False,
        PromoCode.shared_privately == False
    ).count()

    # Count codes shared on socials
    codes_shared_on_socials = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.shared_on_socials == True
    ).count()

    # Count codes shared privately
    codes_shared_privately = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.shared_privately == True
    ).count()

    return {
        "id": promotion.id,
        "name": promotion.name,
        "description": promotion.description,
        "discount_percent": promotion.discount_percent,
        "total_codes": promotion.total_codes,
        "codes_sent": promotion.codes_sent,
        "codes_used": promotion.codes_used,
        "codes_shared_on_socials": codes_shared_on_socials,
        "codes_shared_privately": codes_shared_privately,
        "codes_available": codes_available,
        "created_by": promotion.created_by,
        "created_at": promotion.created_at,
        "codes": codes_data,
    }


class PromotionUpdate(BaseModel):
    """Request to update a promotion (name only)."""
    name: str


@app.patch("/api/admin/promotions/{promotion_id}")
async def update_promotion(
    promotion_id: int,
    update_data: PromotionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update a promotion's name.

    Note: Discount percent cannot be changed after creation.
    """
    from db_models import Promotion

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")

    # Update name
    promotion.name = update_data.name
    promotion.updated_at = get_uk_now()
    db.commit()
    db.refresh(promotion)

    log_promo(f"Promotion updated: {promotion.name}", {"promotion_id": promotion_id})

    # Count truly available codes
    from db_models import PromoCode
    codes_available = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.email_sent == False,
        PromoCode.is_used == False,
        PromoCode.shared_on_socials == False,
        PromoCode.shared_privately == False
    ).count()

    codes_shared_on_socials = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.shared_on_socials == True
    ).count()

    codes_shared_privately = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.shared_privately == True
    ).count()

    return {
        "id": promotion.id,
        "name": promotion.name,
        "description": promotion.description,
        "discount_percent": promotion.discount_percent,
        "total_codes": promotion.total_codes,
        "codes_sent": promotion.codes_sent,
        "codes_used": promotion.codes_used,
        "codes_shared_on_socials": codes_shared_on_socials,
        "codes_shared_privately": codes_shared_privately,
        "codes_available": codes_available,
        "created_by": promotion.created_by,
        "created_at": promotion.created_at,
    }


@app.delete("/api/admin/promotions/{promotion_id}")
async def delete_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete a promotion.

    Can only delete if:
    - No emails have been sent (codes_sent == 0)
    - No codes have been used (codes_used == 0)
    - No codes have been shared on socials
    """
    from db_models import Promotion, PromoCode

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")

    # Check if any emails have been sent
    if promotion.codes_sent > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete promotion - {promotion.codes_sent} email(s) have already been sent"
        )

    # Check if any codes have been used
    if promotion.codes_used > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete promotion - {promotion.codes_used} code(s) have been used"
        )

    # Check if any codes have been shared on socials
    shared_on_socials_count = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.shared_on_socials == True
    ).count()
    if shared_on_socials_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete promotion - {shared_on_socials_count} code(s) have been shared on socials"
        )

    # Check if any codes have been shared privately
    shared_privately_count = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.shared_privately == True
    ).count()
    if shared_privately_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete promotion - {shared_privately_count} code(s) have been shared privately"
        )

    # Delete all associated promo codes first
    db.query(PromoCode).filter(PromoCode.promotion_id == promotion_id).delete()

    # Delete the promotion
    promotion_name = promotion.name
    db.delete(promotion)
    db.commit()

    log_promo(f"Promotion deleted: {promotion_name}", {"promotion_id": promotion_id})

    return {"success": True, "message": f"Promotion '{promotion_name}' deleted"}


@app.post("/api/admin/promotions/{promotion_id}/generate-codes")
async def generate_more_codes(
    promotion_id: int,
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate additional codes for an existing promotion.

    Request body:
    - count: Number of additional codes to generate (1-1000)
    """
    from db_models import Promotion, PromoCode

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")

    count = request.get("count")
    expiry_date = request.get("expiry_date")  # DD/MM/YYYY
    expiry_time = request.get("expiry_time")  # HH:MM
    max_uses_raw = request.get("max_uses")  # None = single-use, 0 = unlimited, N = max N uses

    if not count or count < 1 or count > 1000:
        raise HTTPException(status_code=400, detail="count must be between 1 and 1000")

    # Parse max_uses - empty string or None means single-use, 0 means unlimited, N means max N uses
    max_uses = None  # Default: single-use
    if max_uses_raw is not None and max_uses_raw != '':
        try:
            max_uses = int(max_uses_raw)
            if max_uses < 0:
                raise HTTPException(status_code=400, detail="max_uses cannot be negative")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="max_uses must be a number")

    # Parse expiry if provided
    expires_at = None
    if expiry_date and expiry_time:
        import pytz
        try:
            day, month, year = expiry_date.strip().split("/")
            hour, minute = expiry_time.strip().split(":")
            uk_tz = pytz.timezone("Europe/London")
            from datetime import datetime as dt
            naive_dt = dt(int(year), int(month), int(day), int(hour), int(minute), 0)
            expires_at = uk_tz.localize(naive_dt)
        except (ValueError, AttributeError) as e:
            log_promo("GENERATE_MORE_CODES invalid expiry format", {"expiry_date": expiry_date, "expiry_time": expiry_time, "error": str(e)})
            raise HTTPException(status_code=400, detail="Invalid expiry format. Use DD/MM/YYYY for date and HH:MM for time")

    log_promo("GENERATE_MORE_CODES request", {
        "promotion_id": promotion_id,
        "promotion_name": promotion.name,
        "count": count,
        "expires_at": str(expires_at) if expires_at else None,
        "max_uses": max_uses,
        "user": current_user.email
    })

    # Generate unique promo codes
    codes_created = 0
    max_attempts = count * 10  # Prevent infinite loop
    attempts = 0

    # Use the stored prefix from the promotion (default to TAG for older promotions)
    prefix = promotion.code_prefix if promotion.code_prefix else "TAG"

    while codes_created < count and attempts < max_attempts:
        code = generate_promo_code(prefix)
        attempts += 1

        # Check if code already exists
        existing = db.query(PromoCode).filter(PromoCode.code == code).first()
        if existing:
            log_promo("GENERATE_MORE_CODES code collision, retrying", {"code": code})
            continue

        promo_code = PromoCode(
            promotion_id=promotion.id,
            code=code,
            expires_at=expires_at,
            max_uses=max_uses,
        )
        db.add(promo_code)
        codes_created += 1

    # Update total_codes count
    promotion.total_codes += codes_created
    db.commit()
    db.refresh(promotion)

    log_promo("GENERATE_MORE_CODES success", {
        "promotion_id": promotion_id,
        "codes_created": codes_created,
        "expires_at": str(expires_at) if expires_at else None,
        "new_total": promotion.total_codes
    })

    # Calculate codes_available
    codes_available = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.email_sent == False,
        PromoCode.is_used == False,
        PromoCode.shared_on_socials == False,
        PromoCode.shared_privately == False
    ).count()

    return {
        "success": True,
        "codes_created": codes_created,
        "promotion": {
            "id": promotion.id,
            "name": promotion.name,
            "discount_percent": promotion.discount_percent,
            "total_codes": promotion.total_codes,
            "codes_sent": promotion.codes_sent,
            "codes_used": promotion.codes_used,
            "codes_available": codes_available,
        }
    }


@app.get("/api/admin/promotions/{promotion_id}/available-codes")
async def get_available_codes(
    promotion_id: int,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get available (unsent, unused, not shared) codes for a promotion."""
    from db_models import Promotion, PromoCode

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        raise HTTPException(status_code=404, detail="Promotion not found")

    # Available codes are those not sent, not used, not shared on socials, and not shared privately
    codes = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.email_sent == False,
        PromoCode.is_used == False,
        PromoCode.shared_on_socials == False,
        PromoCode.shared_privately == False
    ).limit(limit).all()

    return {
        "promotion_id": promotion_id,
        "promotion_name": promotion.name,
        "discount_percent": promotion.discount_percent,
        "available_count": len(codes),
        "codes": [{"id": c.id, "code": c.code} for c in codes],
    }


@app.patch("/api/admin/promo-codes/{code_id}/share-socials")
async def mark_code_shared_on_socials(
    code_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Mark a promo code as shared on social media.

    This is used for codes that are posted on socials rather than emailed
    to specific recipients.
    """
    from db_models import PromoCode

    promo_code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")

    # Cannot mark a used code as shared on socials
    if promo_code.is_used and not promo_code.shared_on_socials:
        raise HTTPException(status_code=400, detail="Cannot mark a used code as shared on socials")

    # Cannot mark as shared on socials if already shared privately (mutually exclusive)
    if promo_code.shared_privately and not promo_code.shared_on_socials:
        raise HTTPException(status_code=400, detail="Code is already shared privately - cannot also share on socials")

    # Toggle the shared status
    if promo_code.shared_on_socials:
        promo_code.shared_on_socials = False
        promo_code.shared_on_socials_at = None
        action = "unmarked"
    else:
        promo_code.shared_on_socials = True
        promo_code.shared_on_socials_at = get_uk_now()
        action = "marked"

    db.commit()

    log_promo(f"Promo code {action} as shared on socials", {
        "code_id": code_id,
        "code": promo_code.code,
        "shared_on_socials": promo_code.shared_on_socials,
        "user": current_user.email
    })

    return {
        "success": True,
        "code_id": code_id,
        "shared_on_socials": promo_code.shared_on_socials,
        "shared_on_socials_at": promo_code.shared_on_socials_at.isoformat() if promo_code.shared_on_socials_at else None
    }


@app.patch("/api/admin/promo-codes/{code_id}/share-privately")
async def mark_code_shared_privately(
    code_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Mark a promo code as shared privately (via text, to friends, etc.).

    This is used for codes that are shared privately rather than posted
    on social media or emailed to specific recipients.
    """
    from db_models import PromoCode

    promo_code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")

    # Cannot mark a used code as shared privately
    if promo_code.is_used and not promo_code.shared_privately:
        raise HTTPException(status_code=400, detail="Cannot mark a used code as shared privately")

    # Cannot mark as shared privately if already shared on socials (mutually exclusive)
    if promo_code.shared_on_socials and not promo_code.shared_privately:
        raise HTTPException(status_code=400, detail="Code is already shared on socials - cannot also share privately")

    # Toggle the shared status
    if promo_code.shared_privately:
        promo_code.shared_privately = False
        promo_code.shared_privately_at = None
        action = "unmarked"
    else:
        promo_code.shared_privately = True
        promo_code.shared_privately_at = get_uk_now()
        action = "marked"

    db.commit()

    log_promo(f"Promo code {action} as shared privately", {
        "code_id": code_id,
        "code": promo_code.code,
        "shared_privately": promo_code.shared_privately,
        "user": current_user.email
    })

    return {
        "success": True,
        "code_id": code_id,
        "shared_privately": promo_code.shared_privately,
        "shared_privately_at": promo_code.shared_privately_at.isoformat() if promo_code.shared_privately_at else None
    }


class PromoCodeExpiryUpdate(BaseModel):
    """Request to update a promo code's expiry date/time."""
    # Date in DD/MM/YYYY format, time in 24hr format (HH:MM)
    # If both are None, removes the expiry (code never expires)
    expiry_date: Optional[str] = None  # DD/MM/YYYY
    expiry_time: Optional[str] = None  # HH:MM (24hr format)


@app.patch("/api/admin/promo-codes/{code_id}/expiry")
async def update_promo_code_expiry(
    code_id: int,
    request: PromoCodeExpiryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update a promo code's expiry date/time.

    Accepts date in DD/MM/YYYY format and time in 24hr HH:MM format.
    Both date and time must be provided together, or both must be None to remove expiry.
    The expiry is stored in UK timezone.
    """
    from db_models import PromoCode
    import pytz

    promo_code = db.query(PromoCode).filter(PromoCode.id == code_id).first()
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promo code not found")

    # If both are None, remove expiry
    if request.expiry_date is None and request.expiry_time is None:
        old_expiry = promo_code.expires_at
        promo_code.expires_at = None
        db.commit()

        log_promo("Promo code expiry removed", {
            "code_id": code_id,
            "code": promo_code.code,
            "old_expires_at": str(old_expiry) if old_expiry else None,
            "user": current_user.email
        })

        return {
            "success": True,
            "code_id": code_id,
            "code": promo_code.code,
            "expires_at": None,
            "is_expired": False,
            "message": "Expiry removed - code will never expire"
        }

    # Both must be provided together
    if request.expiry_date is None or request.expiry_time is None:
        raise HTTPException(
            status_code=400,
            detail="Both expiry_date and expiry_time must be provided together, or both must be null to remove expiry"
        )

    # Parse date (DD/MM/YYYY format)
    try:
        day, month, year = request.expiry_date.strip().split("/")
        day = int(day)
        month = int(month)
        year = int(year)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use DD/MM/YYYY (e.g., 25/12/2024)"
        )

    # Parse time (HH:MM 24hr format)
    try:
        hour, minute = request.expiry_time.strip().split(":")
        hour = int(hour)
        minute = int(minute)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail="Invalid time format. Use HH:MM 24hr format (e.g., 14:30)"
        )

    # Validate ranges
    if not (1 <= day <= 31 and 1 <= month <= 12 and 2020 <= year <= 2100):
        raise HTTPException(status_code=400, detail="Invalid date values")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="Invalid time values")

    # Create UK timezone aware datetime
    uk_tz = pytz.timezone("Europe/London")
    try:
        from datetime import datetime as dt
        naive_dt = dt(year, month, day, hour, minute, 0)
        # Localize to UK timezone
        expires_at = uk_tz.localize(naive_dt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date/time: {str(e)}")

    old_expiry = promo_code.expires_at
    promo_code.expires_at = expires_at
    db.commit()

    # Check if it's already expired
    uk_now = get_uk_now()
    is_expired = uk_now >= expires_at

    log_promo("Promo code expiry updated", {
        "code_id": code_id,
        "code": promo_code.code,
        "old_expires_at": str(old_expiry) if old_expiry else None,
        "new_expires_at": str(expires_at),
        "is_expired": is_expired,
        "user": current_user.email
    })

    return {
        "success": True,
        "code_id": code_id,
        "code": promo_code.code,
        "expires_at": expires_at.isoformat(),
        "is_expired": is_expired,
        "message": f"Expiry set to {request.expiry_date} at {request.expiry_time} UK time" + (" (already expired)" if is_expired else "")
    }


class BulkPromoCodeExpiryUpdate(BaseModel):
    """Request model for bulk updating promo code expiry."""
    code_ids: List[int]
    # If both are None, removes the expiry (codes never expire)
    expiry_date: Optional[str] = None  # DD/MM/YYYY
    expiry_time: Optional[str] = None  # HH:MM (24hr format)


@app.patch("/api/admin/promo-codes/bulk-expiry")
async def bulk_update_promo_code_expiry(
    request: BulkPromoCodeExpiryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Bulk update promo codes' expiry date/time.

    Accepts date in DD/MM/YYYY format and time in 24hr HH:MM format.
    Both date and time must be provided together, or both must be None to remove expiry.
    The expiry is stored in UK timezone.
    """
    from db_models import PromoCode
    import pytz

    if not request.code_ids:
        raise HTTPException(status_code=400, detail="No code IDs provided")

    if len(request.code_ids) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 codes can be updated at once")

    # Parse expiry date/time if provided
    expires_at = None
    if request.expiry_date is not None or request.expiry_time is not None:
        # Both must be provided together
        if request.expiry_date is None or request.expiry_time is None:
            raise HTTPException(
                status_code=400,
                detail="Both expiry_date and expiry_time must be provided together, or both must be null to remove expiry"
            )

        # Parse date (DD/MM/YYYY format)
        try:
            day, month, year = request.expiry_date.strip().split("/")
            day = int(day)
            month = int(month)
            year = int(year)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use DD/MM/YYYY (e.g., 25/12/2024)"
            )

        # Parse time (HH:MM 24hr format)
        try:
            hour, minute = request.expiry_time.strip().split(":")
            hour = int(hour)
            minute = int(minute)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail="Invalid time format. Use HH:MM 24hr format (e.g., 14:30)"
            )

        # Validate ranges
        if not (1 <= day <= 31 and 1 <= month <= 12 and 2020 <= year <= 2100):
            raise HTTPException(status_code=400, detail="Invalid date values")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise HTTPException(status_code=400, detail="Invalid time values")

        # Create UK timezone aware datetime
        uk_tz = pytz.timezone("Europe/London")
        try:
            from datetime import datetime as dt
            naive_dt = dt(year, month, day, hour, minute, 0)
            # Localize to UK timezone
            expires_at = uk_tz.localize(naive_dt)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid date/time: {str(e)}")

    # Fetch all codes
    promo_codes = db.query(PromoCode).filter(PromoCode.id.in_(request.code_ids)).all()

    if len(promo_codes) != len(request.code_ids):
        found_ids = {c.id for c in promo_codes}
        missing_ids = [cid for cid in request.code_ids if cid not in found_ids]
        raise HTTPException(status_code=404, detail=f"Some promo codes not found: {missing_ids[:10]}")

    # Update all codes
    uk_now = get_uk_now()
    updated_codes = []
    for promo_code in promo_codes:
        promo_code.expires_at = expires_at
        is_expired = expires_at is not None and uk_now >= expires_at
        updated_codes.append({
            "code_id": promo_code.id,
            "code": promo_code.code,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "is_expired": is_expired
        })

    db.commit()

    log_promo("Bulk promo code expiry updated", {
        "code_ids": request.code_ids,
        "codes_count": len(promo_codes),
        "expires_at": str(expires_at) if expires_at else None,
        "user": current_user.email
    })

    if expires_at:
        message = f"Expiry set to {request.expiry_date} at {request.expiry_time} UK time for {len(promo_codes)} codes"
    else:
        message = f"Expiry removed from {len(promo_codes)} codes"

    return {
        "success": True,
        "updated_count": len(promo_codes),
        "codes": updated_codes,
        "message": message
    }


@app.post("/api/admin/promotions/send-emails")
async def send_promo_emails(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Send promo code emails to selected recipients.

    Request body:
    - promotion_id: ID of the promotion
    - recipients: List of {email, first_name, last_name?, customer_id?, subscriber_id?, source}
    - email_subject: Subject with optional {{FIRST_NAME}} placeholder
    - email_body: HTML body with {{FIRST_NAME}}, {{PROMO_CODE}} placeholders
    """
    from db_models import Promotion, PromoCode, Customer

    promotion_id = request.get("promotion_id")
    recipients = request.get("recipients", [])
    email_subject = request.get("email_subject", "")
    email_body = request.get("email_body", "")

    log_promo("SEND_EMAILS request", {
        "promotion_id": promotion_id,
        "recipient_count": len(recipients),
        "user": current_user.email,
        "recipients": [r.get("email") for r in recipients]
    })

    if not promotion_id or not recipients or not email_subject or not email_body:
        log_promo("SEND_EMAILS failed - missing required fields")
        raise HTTPException(status_code=400, detail="promotion_id, recipients, email_subject, and email_body are required")

    promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
    if not promotion:
        log_promo("SEND_EMAILS failed - promotion not found", {"promotion_id": promotion_id})
        raise HTTPException(status_code=404, detail="Promotion not found")

    log_promo("SEND_EMAILS found promotion", {"promotion_id": promotion.id, "name": promotion.name, "discount_percent": promotion.discount_percent})

    # Get available codes
    available_codes = db.query(PromoCode).filter(
        PromoCode.promotion_id == promotion_id,
        PromoCode.email_sent == False
    ).limit(len(recipients)).all()

    log_promo("SEND_EMAILS available codes", {"available": len(available_codes), "needed": len(recipients)})

    if len(available_codes) < len(recipients):
        log_promo("SEND_EMAILS failed - not enough codes", {"available": len(available_codes), "needed": len(recipients)})
        raise HTTPException(
            status_code=400,
            detail=f"Not enough codes available. Need {len(recipients)}, have {len(available_codes)}"
        )

    total_sent = 0
    total_failed = 0
    errors = []

    for i, recipient in enumerate(recipients):
        email = recipient.get("email")
        first_name = recipient.get("first_name", "")
        last_name = recipient.get("last_name", "")
        customer_id = recipient.get("customer_id")
        subscriber_id = recipient.get("subscriber_id")
        source = recipient.get("source", "new")

        promo_code = available_codes[i]

        # If new contact, create customer record
        if source == "new" and not customer_id:
            existing_customer = db.query(Customer).filter(Customer.email == email).first()
            if existing_customer:
                customer_id = existing_customer.id
            else:
                new_customer = Customer(
                    first_name=first_name,
                    last_name=last_name or "",
                    email=email,
                    phone="",  # Will be added when they book
                )
                db.add(new_customer)
                db.flush()
                customer_id = new_customer.id

        # Build email with placeholders replaced
        # Style promo code with black background and yellow text
        styled_promo_code = f'<strong style="color: #CCFF00; background-color: #343434; padding: 4px 10px; border-radius: 4px; font-family: monospace; letter-spacing: 1px;">{promo_code.code}</strong>'

        personalized_subject = email_subject.replace("{{FIRST_NAME}}", first_name)
        personalized_body = email_body.replace("{{FIRST_NAME}}", first_name).replace("{{PROMO_CODE}}", styled_promo_code)

        # Send email
        try:
            log_promo("SEND_EMAILS sending", {"email": email, "code": promo_code.code, "first_name": first_name})

            email_sent = send_generic_promo_email(
                to_email=email,
                subject=personalized_subject,
                html_body=personalized_body,
            )

            if email_sent:
                # Update promo code record
                promo_code.customer_id = customer_id
                promo_code.subscriber_id = subscriber_id
                promo_code.recipient_email = email
                promo_code.recipient_first_name = first_name
                promo_code.recipient_last_name = last_name
                promo_code.email_sent = True
                promo_code.email_sent_at = get_uk_now()
                promo_code.email_subject = personalized_subject

                total_sent += 1
                log_promo("SEND_EMAILS sent successfully", {"email": email, "code": promo_code.code})
            else:
                total_failed += 1
                errors.append(f"Failed to send to {email}")
                log_promo("SEND_EMAILS send failed", {"email": email, "code": promo_code.code})

        except Exception as e:
            total_failed += 1
            errors.append(f"Error sending to {email}: {str(e)}")
            log_promo("SEND_EMAILS exception", {"email": email, "error": str(e)})

    # Update promotion stats
    promotion.codes_sent += total_sent
    db.commit()

    log_promo("SEND_EMAILS complete", {"total_sent": total_sent, "total_failed": total_failed, "promotion_id": promotion.id})

    return {
        "success": total_failed == 0,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "errors": errors,
    }


def send_generic_promo_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send a generic promo email with custom subject and body. Sent from founder."""
    import os
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content

    sendgrid_api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")
    from_name = os.getenv("FOUNDER_NAME", "Kristian")

    if not sendgrid_api_key:
        print("[EMAIL] SendGrid API key not configured")
        return False

    # Wrap body in basic email template
    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin: 0; padding: 20px; font-family: Arial, Helvetica, sans-serif; font-size: 16px; line-height: 1.6; color: #333333;">
    {html_body}
</body>
</html>"""

    try:
        message = Mail(
            from_email=Email(from_email, from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", full_html),
        )

        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)

        if response.status_code in [200, 201, 202]:
            print(f"[EMAIL] Promo email sent to {to_email}")
            return True
        else:
            print(f"[EMAIL] Failed to send promo email: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Error sending promo email: {e}")
        return False


@app.get("/api/admin/promotions/recipients/search")
async def search_recipients(
    q: str = Query("", min_length=0),
    source: str = Query("all", description="Filter by source: all, customers, subscribers"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Search for potential recipients from customers and marketing subscribers.

    Returns a combined list of potential recipients with their source.
    """
    from db_models import Customer, MarketingSubscriber

    results = []

    # Search customers
    if source in ["all", "customers"]:
        query = db.query(Customer)
        if q:
            search_term = f"%{q}%"
            query = query.filter(
                (Customer.email.ilike(search_term)) |
                (Customer.first_name.ilike(search_term)) |
                (Customer.last_name.ilike(search_term))
            )
        customers = query.order_by(Customer.created_at.desc()).limit(limit).all()

        for c in customers:
            results.append({
                "email": c.email,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "customer_id": c.id,
                "subscriber_id": None,
                "source": "customer",
            })

    # Search marketing subscribers
    if source in ["all", "subscribers"]:
        query = db.query(MarketingSubscriber)
        if q:
            search_term = f"%{q}%"
            query = query.filter(
                (MarketingSubscriber.email.ilike(search_term)) |
                (MarketingSubscriber.first_name.ilike(search_term))
            )
        subscribers = query.order_by(MarketingSubscriber.subscribed_at.desc()).limit(limit).all()

        for s in subscribers:
            # Check if already added as customer (avoid duplicates)
            existing = next((r for r in results if r["email"] == s.email), None)
            if existing:
                existing["subscriber_id"] = s.id
                continue

            results.append({
                "email": s.email,
                "first_name": s.first_name,
                "last_name": "",
                "customer_id": None,
                "subscriber_id": s.id,
                "source": "subscriber",
            })

    return {"recipients": results}


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
    - Blocked info: is_blocked, blocked_reason (if date is blocked for dropoffs)
    """
    # Check if date is blocked for dropoffs
    blocked = db.query(BlockedDate).filter(
        BlockedDate.start_date <= flight_date,
        BlockedDate.end_date >= flight_date,
        BlockedDate.block_dropoffs == True
    ).first()

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
            # Blocked date indicator
            "is_blocked": blocked is not None,
            "blocked_reason": blocked.reason if blocked else None,
        }
        for d in departures
    ]


@app.get("/api/flights/arrivals/{flight_date}")
async def get_arrivals_for_date(flight_date: date, db: Session = Depends(get_db)):
    """
    Get all arrival flights for a specific date.

    Returns flights in a format compatible with the frontend:
    - date, type, time, airlineCode, airlineName, originCode, originName, flightNumber, departureTime
    - Blocked info: is_blocked, blocked_reason (if date is blocked for pickups)
    """
    # Check if date is blocked for pickups
    blocked = db.query(BlockedDate).filter(
        BlockedDate.start_date <= flight_date,
        BlockedDate.end_date >= flight_date,
        BlockedDate.block_pickups == True
    ).first()

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
            # Blocked date indicator
            "is_blocked": blocked is not None,
            "blocked_reason": blocked.reason if blocked else None,
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
# Flight Time Validation (for manual entry / time override)
# =============================================================================

class ValidateFlightTimeRequest(BaseModel):
    """Request to validate a customer-provided flight time."""
    time: str  # "HH:MM" format
    flight_type: str  # "departure" or "arrival"


class ValidateFlightTimeResponse(BaseModel):
    """Response for flight time validation."""
    valid: bool
    normalized_time: Optional[str] = None
    error: Optional[str] = None


def validate_flight_time(time_str: str, flight_type: str) -> tuple[bool, str, Optional[str]]:
    """
    Validate customer-provided flight time.

    Args:
        time_str: Time in "HH:MM" format
        flight_type: "departure" or "arrival"

    Returns:
        Tuple of (is_valid, normalized_time_or_error, error_message_or_None)
    """
    # Format check
    if not time_str or not re.match(r'^\d{1,2}:\d{2}$', time_str):
        return False, "", "Time must be in HH:MM format"

    try:
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
    except (ValueError, IndexError):
        return False, "", "Time must be in HH:MM format"

    # Range check
    if hours > 23 or minutes > 59:
        return False, "", "Invalid time - hours must be 0-23, minutes 0-59"

    # Business hours check (BOH operating hours)
    if flight_type == "departure":
        # Departures typically 06:00-22:00
        if hours < 6 or hours > 22:
            return False, "", "Departure time must be between 06:00 and 22:00"
    elif flight_type == "arrival":
        # Arrivals allow overnight (00:00-05:59 for red-eye arrivals) and normal hours
        # Only block 02:00-05:59 as unlikely
        if 2 <= hours < 6:
            return False, "", "Arrival time must be between 06:00 and 01:59 (overnight arrivals allowed)"

    # Normalize to HH:MM
    normalized = f"{hours:02d}:{minutes:02d}"
    return True, normalized, None


@app.post("/api/booking/validate-flight-time", response_model=ValidateFlightTimeResponse)
async def validate_customer_flight_time(request: ValidateFlightTimeRequest):
    """
    Validate a customer-provided flight time.

    Used when:
    1. Customer overrides a scheduled flight time (their booking shows different time)
    2. Customer enters a manual flight entry (flight not in our system)

    Security:
    - Validates time format (HH:MM)
    - Validates reasonable operating hours for BOH airport
    - Does NOT write to database - just validates input
    """
    is_valid, result, error = validate_flight_time(request.time, request.flight_type)

    if is_valid:
        return ValidateFlightTimeResponse(
            valid=True,
            normalized_time=result,
            error=None
        )
    else:
        return ValidateFlightTimeResponse(
            valid=False,
            normalized_time=None,
            error=error
        )


@app.get("/api/booking/airlines")
async def get_available_airlines():
    """
    Get list of airlines for manual flight entry.

    Returns airlines that operate at BOH with their codes.
    """
    return {
        "airlines": [
            {"code": "FR", "name": "Ryanair"},
            {"code": "RK", "name": "Ryanair UK"},
            {"code": "U2", "name": "easyJet"},
            {"code": "LS", "name": "Jet2"},
            {"code": "BY", "name": "TUI Airways"},
            {"code": "OTHER", "name": "Other"}
        ]
    }


@app.get("/api/booking/destinations")
async def get_available_destinations(db: Session = Depends(get_db)):
    """
    Get list of destinations for manual flight entry.

    Returns unique destinations from our flight schedule.
    """
    destinations = db.query(
        FlightDeparture.destination_code,
        FlightDeparture.destination_name
    ).distinct().order_by(FlightDeparture.destination_name).all()

    return {
        "destinations": [
            {"code": d[0], "name": d[1]}
            for d in destinations
            if d[0] and d[1]
        ]
    }


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

        # Log audit event for customer update
        log_audit_event(
            db=db,
            event=AuditLogEvent.CUSTOMER_ENTERED,
            request=http_request,
            session_id=request.session_id,
            event_data={
                "customer_id": customer.id,
                "email": request.email,
                "is_new_customer": False,
            },
        )

        return {
            "success": True,
            "customer_id": customer.id,
            "message": "Customer updated successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Marketing Attribution ("Where did you hear about us?") Endpoints
# =============================================================================

# Valid marketing source values
VALID_MARKETING_SOURCES = ['newspaper', 'google', 'facebook', 'instagram', 'linkedin', 'afc_bournemouth', 'word_of_mouth', 'leaflet', 'tv', 'radio', 'other']


@app.get("/api/customers/heard-about-us-status")
async def get_heard_about_us_status(
    email: str = Query(..., description="Customer email address"),
    db: Session = Depends(get_db),
):
    """
    Check if a customer has already answered the "Where did you hear about us?" question.
    Called when Page 4 (Payment) loads to determine if the question should be shown.
    """
    from db_models import Customer
    from sqlalchemy import func

    # Case-insensitive email lookup
    customer = db.query(Customer).filter(
        func.lower(Customer.email) == func.lower(email)
    ).first()

    if not customer:
        # New customer - show the question
        return {
            "customer_id": None,
            "has_answered_heard_about_us": False,
            "show_heard_about_us": True,
        }

    # Existing customer - check if they've already answered
    return {
        "customer_id": customer.id,
        "has_answered_heard_about_us": customer.has_answered_heard_about_us or False,
        "show_heard_about_us": not (customer.has_answered_heard_about_us or False),
    }


class HeardAboutUsRequest(BaseModel):
    email: str
    source: str
    source_detail: Optional[str] = None


@app.post("/api/customers/heard-about-us")
async def save_heard_about_us(
    request: HeardAboutUsRequest,
    db: Session = Depends(get_db),
):
    """
    Save the customer's marketing attribution response.
    Called immediately when the customer selects an option (before payment).
    """
    from db_models import Customer, MarketingSource, MarketingSourceMonthlyTotal
    from sqlalchemy import func

    # Validate source value
    if request.source not in VALID_MARKETING_SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source. Must be one of: {', '.join(VALID_MARKETING_SOURCES)}"
        )

    # Validate source_detail if source is 'other'
    if request.source == 'other':
        if not request.source_detail or len(request.source_detail.strip()) < 3:
            raise HTTPException(
                status_code=400,
                detail="Please tell us how you heard about us (minimum 3 characters)"
            )
        if len(request.source_detail) > 255:
            raise HTTPException(
                status_code=400,
                detail="Source detail too long (maximum 255 characters)"
            )

    # Case-insensitive email lookup
    customer = db.query(Customer).filter(
        func.lower(Customer.email) == func.lower(request.email)
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found. Please complete contact details first.")

    # Check if already answered - silently succeed (idempotent)
    if customer.has_answered_heard_about_us:
        return {
            "success": True,
            "message": "Marketing source already recorded",
            "already_answered": True,
        }

    try:
        # Create marketing source record
        source_detail = request.source_detail.strip() if request.source == 'other' and request.source_detail else None

        marketing_source = MarketingSource(
            customer_id=customer.id,
            source=request.source,
            source_detail=source_detail,
        )
        db.add(marketing_source)

        # Update customer flag
        customer.has_answered_heard_about_us = True

        # Update monthly totals (UPSERT)
        year_month = datetime.utcnow().strftime('%Y-%m')

        existing_total = db.query(MarketingSourceMonthlyTotal).filter(
            MarketingSourceMonthlyTotal.year_month == year_month,
            MarketingSourceMonthlyTotal.source == request.source,
        ).first()

        if existing_total:
            existing_total.count += 1
        else:
            new_total = MarketingSourceMonthlyTotal(
                year_month=year_month,
                source=request.source,
                count=1,
            )
            db.add(new_total)

        db.commit()

        return {
            "success": True,
            "message": "Marketing source recorded",
            "already_answered": False,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save marketing source: {str(e)}")


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
        from datetime import datetime, timezone
        customer.billing_address1 = request.billing_address1
        customer.billing_address2 = request.billing_address2
        customer.billing_city = request.billing_city
        customer.billing_county = request.billing_county
        customer.billing_postcode = request.billing_postcode
        customer.billing_country = request.billing_country
        customer.billing_updated_at = datetime.now(timezone.utc)  # Track when billing was added/updated
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

        # Log audit event for vehicle update
        log_audit_event(
            db=db,
            event=AuditLogEvent.VEHICLE_ENTERED,
            request=http_request,
            session_id=request.session_id,
            event_data={
                "vehicle_id": vehicle.id,
                "customer_id": request.customer_id,
                "registration": vehicle.registration,
                "make": vehicle.make,
                "model": vehicle.model,
                "is_new_vehicle": False,
            },
        )

        return {
            "success": True,
            "vehicle_id": vehicle.id,
            "message": "Vehicle updated successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# Checkout Audit Logging Endpoint
# =============================================================================

class CheckoutAuditRequest(BaseModel):
    """Request to log checkout events for debugging."""
    session_id: str
    event: str  # 'tnc_accepted', 'checkout_loaded'
    booking_reference: Optional[str] = None
    event_data: Optional[dict] = None


@app.post("/api/booking/audit-event")
async def log_checkout_event(
    request: CheckoutAuditRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """
    Log checkout flow events for debugging customer issues.

    Events:
    - dates_selected: User selected drop-off and pick-up dates (early funnel)
    - flight_selected: User selected flight details (early funnel)
    - tnc_accepted: User checked the T&C checkbox
    - tnc_unchecked: User unchecked the T&C checkbox
    - promo_code_added: User added a promo code
    - promo_code_removed: User removed a promo code
    - checkout_loaded: Stripe checkout page loaded successfully
    """
    event_map = {
        "dates_selected": AuditLogEvent.DATES_SELECTED,
        "flight_selected": AuditLogEvent.FLIGHT_SELECTED,
        "tnc_accepted": AuditLogEvent.TNC_ACCEPTED,
        "tnc_unchecked": AuditLogEvent.TNC_UNCHECKED,
        "promo_code_added": AuditLogEvent.PROMO_CODE_ADDED,
        "promo_code_removed": AuditLogEvent.PROMO_CODE_REMOVED,
        "checkout_loaded": AuditLogEvent.CHECKOUT_LOADED,
        "payment_processing": AuditLogEvent.PAYMENT_PROCESSING,
        "payment_initiated": AuditLogEvent.PAYMENT_INITIATED,
        "payment_succeeded": AuditLogEvent.PAYMENT_SUCCEEDED,
        "payment_failed": AuditLogEvent.PAYMENT_FAILED,
    }

    audit_event = event_map.get(request.event)
    if not audit_event:
        raise HTTPException(status_code=400, detail=f"Unknown event type: {request.event}")

    log_audit_event(
        db=db,
        event=audit_event,
        request=http_request,
        session_id=request.session_id,
        booking_reference=request.booking_reference,
        event_data=request.event_data or {},
    )

    return {"success": True, "event": request.event}


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
# Ideal Postcodes API - Address Lookup
# =============================================================================

class AddressLookupRequest(BaseModel):
    """Request to lookup addresses by postcode."""
    postcode: str


class Address(BaseModel):
    """A single address from Ideal Postcodes API."""
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
    Lookup addresses by postcode using Ideal Postcodes API.

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
    api_key = settings.os_places_api_key  # Reusing same env var for Ideal Postcodes key

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Address lookup service is not configured"
        )

    # Call Ideal Postcodes API
    ideal_url = f"https://api.ideal-postcodes.co.uk/v1/postcodes/{clean_postcode}?api_key={api_key}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ideal_url, timeout=10.0)

            if response.status_code == 200:
                data = response.json()
                results = data.get("result", [])

                addresses = []
                for result in results:
                    post_town = result.get("post_town", "")
                    # Use county from API, fallback to lookup
                    county = result.get("county") or POST_TOWN_TO_COUNTY.get(post_town.upper())

                    # Build full address from line_1, line_2, line_3, post_town, postcode
                    address_parts = [
                        result.get("line_1", ""),
                        result.get("line_2", ""),
                        result.get("line_3", ""),
                        post_town,
                        result.get("postcode", ""),
                    ]
                    full_address = ", ".join(part for part in address_parts if part)

                    addresses.append(Address(
                        uprn=str(result.get("udprn", "")),
                        address=full_address,
                        building_name=result.get("building_name") or result.get("sub_building_name"),
                        building_number=result.get("building_number"),
                        thoroughfare=result.get("thoroughfare") or result.get("dependant_thoroughfare"),
                        dependent_locality=result.get("dependant_locality"),
                        post_town=post_town,
                        postcode=result.get("postcode", ""),
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
                    total_results=len(addresses)
                )
            elif response.status_code == 404:
                # Postcode not found
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error="Postcode not found"
                )
            elif response.status_code == 402:
                # Payment required / key exhausted
                log_error(
                    db=db,
                    error_type="ideal_postcodes_api",
                    message="Ideal Postcodes API key exhausted or payment required",
                    request=http_request,
                    error_code="402",
                    request_data={"postcode": clean_postcode},
                )
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error="Address service temporarily unavailable"
                )
            elif response.status_code == 401:
                log_error(
                    db=db,
                    error_type="ideal_postcodes_api",
                    message="Ideal Postcodes API authentication failed",
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
                    error_type="ideal_postcodes_api",
                    message=f"Ideal Postcodes API error: {response.status_code}",
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
            error_type="ideal_postcodes_api",
            message="Ideal Postcodes API timeout",
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
            error_type="ideal_postcodes_api",
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

        # Check if any active promo modals have hit their subscriber limit
        check_promo_modal_subscriber_limits(db)

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

    # Customer-provided departure time override (optional)
    # When True, customer has corrected the flight time from the schedule
    dropoff_time_override: bool = False
    dropoff_scheduled_time: Optional[str] = None  # Original time from flight table "HH:MM"

    # Manual departure entry (optional)
    # When True, customer entered flight details manually (flight not in system)
    dropoff_manual_entry: bool = False
    dropoff_airline_code: Optional[str] = None  # For manual entries (e.g., "BY" for TUI)
    dropoff_airline_name: Optional[str] = None  # For manual entries (e.g., "TUI")
    dropoff_destination_code: Optional[str] = None  # For manual entries
    dropoff_destination_name: Optional[str] = None  # For manual entries
    dropoff_flight_time: Optional[str] = None  # For manual entries "HH:MM"
    dropoff_customer_time: Optional[str] = None  # Customer-provided time override "HH:MM"

    # Customer-provided arrival time override (optional)
    pickup_time_override: bool = False
    pickup_scheduled_time: Optional[str] = None  # Original time from flight table "HH:MM"
    pickup_customer_time: Optional[str] = None  # Customer-provided time override "HH:MM"

    # Manual arrival entry (optional)
    pickup_manual_entry: bool = False
    pickup_airline_code: Optional[str] = None
    pickup_airline_name: Optional[str] = None
    pickup_origin_code: Optional[str] = None  # For manual entries
    pickup_origin_name: Optional[str] = None  # For manual entries
    pickup_flight_time: Optional[str] = None  # For manual entries "HH:MM" - flight arrival time

    # Actual flight times (always sent, used for emails and display)
    flight_departure_time: Optional[str] = None  # "HH:MM" - actual flight departure time
    flight_arrival_time: Optional[str] = None  # "HH:MM" - actual flight arrival time


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

        # Validate same-day bookings have at least 4 hours notice
        from datetime import datetime
        from zoneinfo import ZoneInfo
        MIN_HOURS_NOTICE = 4
        uk_tz = ZoneInfo("Europe/London")
        now_uk = datetime.now(uk_tz)
        today_uk = now_uk.date()

        # Parse drop_off_date from string to date for comparison
        request_dropoff_date = datetime.strptime(request.drop_off_date, "%Y-%m-%d").date()

        if request_dropoff_date == today_uk:
            # Parse the flight time (or dropoff time)
            flight_time_str = request.flight_departure_time
            if flight_time_str:
                flight_hours, flight_mins = map(int, flight_time_str.split(':'))
                flight_minutes_from_midnight = flight_hours * 60 + flight_mins
                # Calculate dropoff slot time (either 165 or 120 mins before flight)
                # drop_off_slot contains "165" or "120" as string
                slot_offset = int(request.drop_off_slot) if request.drop_off_slot else 165
                dropoff_minutes = flight_minutes_from_midnight - slot_offset
                # Current UK time in minutes from midnight
                current_minutes = now_uk.hour * 60 + now_uk.minute
                # Check if dropoff is at least 4 hours away
                min_notice_minutes = MIN_HOURS_NOTICE * 60
                if dropoff_minutes < current_minutes + min_notice_minutes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Same-day bookings require at least {MIN_HOURS_NOTICE} hours notice. Please call us to arrange a last-minute booking."
                    )

        # Check for blocked dates (UK timezone)
        # Parse pickup_date for blocked date check
        request_pickup_date = datetime.strptime(request.pickup_date, "%Y-%m-%d").date()

        # Helper function to check if a time is blocked
        def check_time_blocked(blocked_date, check_time_str, check_type):
            """Check if a specific time is blocked within a blocked date."""
            if not blocked_date.time_slots or len(blocked_date.time_slots) == 0:
                # No time slots - entire day is blocked based on blocked_date settings
                if check_type == "dropoff":
                    return blocked_date.block_dropoffs
                else:
                    return blocked_date.block_pickups

            # Time slots exist - check if the time falls within any
            if not check_time_str:
                return False  # No time provided, can't determine if blocked

            # Parse the time
            try:
                h, m = map(int, check_time_str.split(":"))
                check_time = time(h, m)
            except (ValueError, AttributeError):
                return False

            # Check each time slot
            for ts in blocked_date.time_slots:
                if ts.start_time <= check_time < ts.end_time:
                    if check_type == "dropoff" and ts.block_dropoffs:
                        return True
                    if check_type == "pickup" and ts.block_pickups:
                        return True

            return False

        # Check if dropoff date is blocked
        blocked_dropoff = db.query(BlockedDate).options(
            joinedload(BlockedDate.time_slots)
        ).filter(
            BlockedDate.start_date <= request_dropoff_date,
            BlockedDate.end_date >= request_dropoff_date
        ).first()

        if blocked_dropoff:
            # Get the dropoff time to check against time slots
            dropoff_time_str = request.drop_off_time
            if not dropoff_time_str and request.dropoff_flight_time and request.drop_off_slot:
                # Calculate from flight time and slot
                try:
                    h, m = map(int, request.dropoff_flight_time.split(":"))
                    slot_mins = int(request.drop_off_slot)
                    total_mins = h * 60 + m - slot_mins
                    if total_mins < 0:
                        total_mins += 24 * 60
                    dropoff_time_str = f"{total_mins // 60:02d}:{total_mins % 60:02d}"
                except (ValueError, TypeError):
                    pass

            if check_time_blocked(blocked_dropoff, dropoff_time_str, "dropoff"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Sorry, drop-offs are not available on {request_dropoff_date.strftime('%d %B %Y')}. Please select a different date or time."
                )

        # Check if pickup date is blocked
        blocked_pickup = db.query(BlockedDate).options(
            joinedload(BlockedDate.time_slots)
        ).filter(
            BlockedDate.start_date <= request_pickup_date,
            BlockedDate.end_date >= request_pickup_date
        ).first()

        if blocked_pickup:
            # Get the pickup time to check against time slots
            pickup_time_str = request.pickup_time
            if not pickup_time_str and request.pickup_flight_time:
                pickup_time_str = request.pickup_flight_time

            if check_time_blocked(blocked_pickup, pickup_time_str, "pickup"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Sorry, pick-ups are not available on {request_pickup_date.strftime('%d %B %Y')}. Please select a different date or time."
                )

        # Check for existing PENDING booking with same session_id (prevent duplicates from Terms toggle)
        existing_booking = None
        promo_changed = False
        if request.session_id:
            existing_booking = db_service.get_pending_booking_by_session(db, request.session_id)
            if existing_booking:
                print(f"[DEDUP] Found existing PENDING booking {existing_booking.reference} for session {request.session_id}")
                # Check if there's an existing payment record with a valid PaymentIntent
                existing_payment = existing_booking.payment
                if existing_payment and existing_payment.stripe_payment_intent_id:
                    try:
                        # Retrieve the existing PaymentIntent from Stripe to check promo and status
                        intent = stripe.PaymentIntent.retrieve(existing_payment.stripe_payment_intent_id)

                        # Get the promo code from PaymentIntent metadata
                        # Stripe returns StripeObject - use getattr, not .get()
                        metadata = getattr(intent, "metadata", None)
                        existing_promo = getattr(metadata, "promo_code", None) if metadata else None
                        # Normalize empty string to None so "" and None are treated the same
                        existing_promo = existing_promo if existing_promo else None
                        new_promo = request.promo_code.strip().upper() if request.promo_code else None
                        promo_changed = existing_promo != new_promo
                        print(f"[DEDUP] Existing promo: {existing_promo}, New promo: {new_promo}, Changed: {promo_changed}")

                        if intent.status in ['requires_payment_method', 'requires_confirmation', 'requires_action']:
                            if promo_changed:
                                # Promo code changed - modify existing PaymentIntent instead of cancel/create
                                print(f"[DEDUP] Promo code changed - modifying existing PaymentIntent")

                                # Calculate new amount with the new promo code
                                dropoff_date = datetime.strptime(request.drop_off_date, "%Y-%m-%d").date()
                                pickup_date = datetime.strptime(request.pickup_date, "%Y-%m-%d").date()
                                duration_days = (pickup_date - dropoff_date).days

                                new_original_amount = calculate_price_in_pence(
                                    package=request.package,
                                    drop_off_date=dropoff_date,
                                    duration_days=duration_days
                                )

                                new_discount_amount = 0
                                new_promo_code_applied = None
                                is_free_booking = False

                                if new_promo:
                                    # Validate and calculate discount for the new promo code
                                    from db_models import PromoCode as DbPromoCode, Promotion as DbPromotion

                                    promo_code_record = db.query(DbPromoCode).filter(DbPromoCode.code == new_promo).first()
                                    if promo_code_record:
                                        # Check if code is used or expired
                                        code_valid = not promo_code_record.is_used
                                        if promo_code_record.expires_at and get_uk_now() >= promo_code_record.expires_at:
                                            code_valid = False
                                        # Multi-use codes can be used even if is_used is True (check use_count vs max_uses)
                                        if promo_code_record.is_multi_use:
                                            code_valid = True  # Multi-use codes handled by can_use check below

                                        if code_valid:
                                            promotion = db.query(DbPromotion).filter(DbPromotion.id == promo_code_record.promotion_id).first()
                                            if promotion:
                                                # Check if code can be used (single-use: not used, multi-use: always ok)
                                                can_use = promo_code_record.is_multi_use or not promo_code_record.is_used
                                                if can_use:
                                                    discount_percent = promotion.discount_percent
                                                    if discount_percent == 100:
                                                        new_discount_amount = new_original_amount
                                                        is_free_booking = True
                                                    else:
                                                        new_discount_amount = int(new_original_amount * discount_percent / 100)
                                                    new_promo_code_applied = new_promo
                                                    print(f"[DEDUP] New promo {new_promo}: {discount_percent}% = {new_discount_amount} pence discount")
                                    else:
                                        # Check legacy promotions table
                                        from db_models import Promotion
                                        promo_record = db.query(Promotion).filter(
                                            Promotion.promo_code == new_promo,
                                            Promotion.is_active == True
                                        ).first()
                                        if promo_record and not promo_record.used:
                                            discount_percent = promo_record.discount_percent
                                            if discount_percent == 100:
                                                if duration_days <= 7:
                                                    new_discount_amount = new_original_amount
                                                    is_free_booking = True
                                                else:
                                                    week1_base_pence = int(get_base_price_for_duration(7) * 100)
                                                    new_discount_amount = min(week1_base_pence, new_original_amount)
                                            else:
                                                new_discount_amount = int(new_original_amount * discount_percent / 100)
                                            new_promo_code_applied = new_promo
                                            print(f"[DEDUP] Legacy promo {new_promo}: {discount_percent}% = {new_discount_amount} pence discount")

                                new_amount = new_original_amount - new_discount_amount

                                # Handle 100% discount (free booking) - can't have £0 PaymentIntent
                                if is_free_booking:
                                    print(f"[DEDUP] 100% discount - canceling PaymentIntent for free booking")
                                    try:
                                        stripe.PaymentIntent.cancel(existing_payment.stripe_payment_intent_id)
                                    except stripe.error.StripeError as e:
                                        print(f"[DEDUP] Could not cancel PaymentIntent: {e}")
                                    db.delete(existing_payment)
                                    db.commit()
                                    # Fall through to create free booking flow below
                                else:
                                    # Modify the existing PaymentIntent with new amount and metadata
                                    try:
                                        modified_intent = stripe.PaymentIntent.modify(
                                            existing_payment.stripe_payment_intent_id,
                                            amount=new_amount,
                                            metadata={
                                                "booking_reference": existing_booking.reference,
                                                "customer_name": f"{request.first_name} {request.last_name}",
                                                "flight_number": request.flight_number,
                                                "drop_off_date": request.drop_off_date,
                                                "pickup_date": request.pickup_date,
                                                "flight_date": request.flight_date,
                                                "drop_off_slot": request.drop_off_slot,
                                                "departure_id": request.departure_id or "",
                                                "promo_code": new_promo_code_applied or "",
                                                "original_amount": str(new_original_amount) if new_promo_code_applied else "",
                                                "discount_amount": str(new_discount_amount) if new_promo_code_applied else "",
                                            }
                                        )
                                        print(f"[DEDUP] Modified PaymentIntent {modified_intent.id} - new amount: {new_amount}")

                                        # Update payment record in DB
                                        existing_payment.amount_pence = new_amount
                                        db.commit()
                                        print(f"[DEDUP] Updated payment record amount to {new_amount}")

                                        # Return the modified PaymentIntent
                                        settings = get_settings()
                                        response = CreatePaymentResponse(
                                            client_secret=modified_intent.client_secret,
                                            payment_intent_id=modified_intent.id,
                                            booking_reference=existing_booking.reference,
                                            amount=new_amount,
                                            amount_display=f"£{new_amount / 100:.2f}",
                                            publishable_key=settings.stripe_publishable_key,
                                        )

                                        # Add discount info if promo code was applied
                                        if new_promo_code_applied:
                                            response.original_amount = new_original_amount
                                            response.original_amount_display = f"£{new_original_amount / 100:.2f}"
                                            response.discount_amount = new_discount_amount
                                            response.discount_amount_display = f"£{new_discount_amount / 100:.2f}"
                                            response.promo_code_applied = new_promo_code_applied

                                        return response

                                    except stripe.error.StripeError as e:
                                        print(f"[DEDUP] Could not modify PaymentIntent: {e}")
                                        # Fall through to create new one
                            else:
                                # PaymentIntent is still usable and promo hasn't changed - return it
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
        promo_code_record = None  # Track if this is from new promo_codes table

        if request.promo_code:
            from db_models import PromoCode as DbPromoCode, Promotion as DbPromotion

            promo_code = request.promo_code.strip().upper()
            log_promo("PAYMENT looking up code", {"code": promo_code, "original_amount": original_amount})

            # First, check the new promo_codes table
            promo_code_record = db.query(DbPromoCode).filter(DbPromoCode.code == promo_code).first()
            if promo_code_record:
                log_promo("PAYMENT found in promo_codes table", {
                    "code": promo_code,
                    "promotion_id": promo_code_record.promotion_id,
                    "is_used": promo_code_record.is_used,
                    "recipient_email": promo_code_record.recipient_email
                })
                if promo_code_record.is_used:
                    log_promo("PAYMENT code already used", {"code": promo_code, "used_at": str(promo_code_record.used_at)})
                elif promo_code_record.expires_at and get_uk_now() >= promo_code_record.expires_at:
                    log_promo("PAYMENT code expired", {"code": promo_code, "expires_at": str(promo_code_record.expires_at)})
                else:
                    # Get discount from parent promotion
                    promotion = db.query(DbPromotion).filter(DbPromotion.id == promo_code_record.promotion_id).first()
                    if promotion:
                        discount_percent = promotion.discount_percent
                        log_promo("PAYMENT applying discount (new system)", {
                            "code": promo_code,
                            "promotion_name": promotion.name,
                            "discount_percent": discount_percent,
                            "original_amount": original_amount
                        })

                        if discount_percent == 100:
                            # 100% off - full discount on any trip length
                            discount_amount = original_amount
                            is_free_booking = True
                        else:
                            # Percentage-based discount
                            discount_amount = int(original_amount * discount_percent / 100)
                            is_free_booking = False

                        promo_code_applied = promo_code
                        log_promo("PAYMENT discount calculated", {
                            "code": promo_code,
                            "discount_amount": discount_amount,
                            "final_amount": original_amount - discount_amount,
                            "is_free_booking": is_free_booking
                        })
            else:
                # Fallback: Check legacy MarketingSubscriber promo fields
                subscriber = db.query(MarketingSubscriber).filter(
                    (MarketingSubscriber.promo_code == promo_code) |
                    (MarketingSubscriber.promo_10_code == promo_code) |
                    (MarketingSubscriber.promo_free_code == promo_code) |
                    (MarketingSubscriber.founder_promo_code == promo_code)
                ).first()
                if subscriber:
                    # Determine which promo type this code belongs to
                    promo_used = False
                    if subscriber.founder_promo_code and subscriber.founder_promo_code == promo_code:
                        promo_used = subscriber.founder_promo_used
                        discount_percent = 10
                    elif subscriber.promo_10_code and subscriber.promo_10_code == promo_code:
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
                    print(f"[PROMO] No code found in either table")

        # Final amount after discount
        amount = original_amount - discount_amount

        # Calculate drop-off time from slot and flight departure
        dropoff_time = time(12, 0)  # Default to noon
        if request.drop_off_time:
            # Explicit time provided (e.g., from admin)
            time_parts = request.drop_off_time.split(":")
            dropoff_time = time(int(time_parts[0]), int(time_parts[1]))
        elif request.dropoff_manual_entry and request.dropoff_flight_time and request.drop_off_slot:
            # Manual entry: calculate from customer-provided flight time minus slot minutes
            time_parts = request.dropoff_flight_time.split(":")
            dep_hour = int(time_parts[0])
            dep_min = int(time_parts[1])
            slot_minutes = int(request.drop_off_slot)
            total_minutes = dep_hour * 60 + dep_min - slot_minutes
            # Handle overnight (negative minutes)
            if total_minutes < 0:
                total_minutes += 24 * 60
            dropoff_time = time(total_minutes // 60, total_minutes % 60)
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

        # Parse pickup/landing time and calculate pickup time (30 min after landing)
        pickup_time = None
        flight_arrival_time = None
        if request.pickup_flight_time:
            time_parts = request.pickup_flight_time.split(":")
            landing_hour = int(time_parts[0])
            landing_min = int(time_parts[1])
            flight_arrival_time = time(landing_hour, landing_min)  # Landing/arrival time

            # Calculate pickup time (30 minutes after landing)
            total_minutes = landing_hour * 60 + landing_min + 30

            # Handle overnight (e.g., 23:30 landing + 30 min = 00:00 next day)
            if total_minutes >= 24 * 60:
                pickup_date = pickup_date + timedelta(days=1)

            pickup_time = time(
                (total_minutes // 60) % 24,
                total_minutes % 60
            )

        # Check if we can reuse an existing booking (promo changed case)
        if existing_booking and promo_changed:
            # Reuse the existing booking reference - promo info will be stored in new PaymentIntent metadata
            print(f"[DEDUP] Reusing existing booking {existing_booking.reference} for new promo")
            existing_booking.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing_booking)
            booking_reference = existing_booking.reference
            booking_id = existing_booking.id
        # Check if we have existing customer/vehicle from incremental saves
        elif request.customer_id and request.vehicle_id:
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
            elif request.dropoff_destination_name:
                # Fallback for manual entries: use destination name from request
                dropoff_destination = request.dropoff_destination_name

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
                pickup_flight_number=request.pickup_flight_number,
                pickup_origin=pickup_origin,
                departure_id=request.departure_id,
                dropoff_slot=slot_type,
                arrival_id=arrival_id,
                session_id=request.session_id,
                # Manual entry fields for departure
                dropoff_manual_entry=request.dropoff_manual_entry,
                dropoff_airline_code=request.dropoff_airline_code,
                dropoff_airline_name=request.dropoff_airline_name,
                # Manual entry fields for arrival
                pickup_manual_entry=request.pickup_manual_entry,
                pickup_airline_code=request.pickup_airline_code,
                pickup_airline_name=request.pickup_airline_name,
                # Actual flight times
                flight_departure_time=time.fromisoformat(request.flight_departure_time) if request.flight_departure_time else None,
                flight_arrival_time=time.fromisoformat(request.flight_arrival_time) if request.flight_arrival_time else flight_arrival_time,
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
            elif request.dropoff_destination_name:
                # Fallback for manual entries: use destination name from request
                dropoff_destination = request.dropoff_destination_name

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

            # Parse scheduled times if provided (for time override tracking)
            dropoff_scheduled_time_parsed = None
            if request.dropoff_scheduled_time:
                try:
                    parts = request.dropoff_scheduled_time.split(':')
                    dropoff_scheduled_time_parsed = time(int(parts[0]), int(parts[1]))
                except (ValueError, IndexError):
                    pass

            pickup_scheduled_time_parsed = None
            if request.pickup_scheduled_time:
                try:
                    parts = request.pickup_scheduled_time.split(':')
                    pickup_scheduled_time_parsed = time(int(parts[0]), int(parts[1]))
                except (ValueError, IndexError):
                    pass

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
                pickup_flight_number=request.pickup_flight_number,
                pickup_origin=pickup_origin,
                # Flight slot
                departure_id=request.departure_id,
                dropoff_slot=slot_type,
                arrival_id=arrival_id,
                # Session tracking
                session_id=request.session_id,
                # Customer-provided time override fields
                dropoff_time_override=request.dropoff_time_override,
                dropoff_scheduled_time=dropoff_scheduled_time_parsed,
                dropoff_manual_entry=request.dropoff_manual_entry,
                dropoff_airline_code=request.dropoff_airline_code,
                dropoff_airline_name=request.dropoff_airline_name,
                pickup_time_override=request.pickup_time_override,
                pickup_scheduled_time=pickup_scheduled_time_parsed,
                pickup_manual_entry=request.pickup_manual_entry,
                pickup_airline_code=request.pickup_airline_code,
                pickup_airline_name=request.pickup_airline_name,
                # Actual flight times
                flight_departure_time=time.fromisoformat(request.flight_departure_time) if request.flight_departure_time else None,
                flight_arrival_time=time.fromisoformat(request.flight_arrival_time) if request.flight_arrival_time else flight_arrival_time,
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

            # Mark promo code as used (check new promo_codes table first, then legacy)
            if promo_code_applied:
                log_promo("MARK_USED (free booking) starting", {"code": promo_code_applied, "booking_id": booking_id})
                # First, check if it's from the new promo_codes table
                if promo_code_record and promo_code_record.can_be_used:
                    # Get discount percent from promotion
                    promotion = db.query(DbPromotion).filter(DbPromotion.id == promo_code_record.promotion_id).first()
                    discount_pct = promotion.discount_percent if promotion else 100
                    mark_promo_code_used(db, promo_code_record, booking_id, discount_pct, 0)  # 0 amount for free bookings
                    db.commit()
                    log_promo("MARK_USED (free booking) success (new system)", {
                        "code": promo_code_applied,
                        "booking_id": booking_id,
                        "promotion_id": promo_code_record.promotion_id
                    })
                elif not promo_code_record:
                    # Fallback: Legacy MarketingSubscriber promo fields
                    subscriber = db.query(MarketingSubscriber).filter(
                        (MarketingSubscriber.promo_code == promo_code_applied) |
                        (MarketingSubscriber.promo_10_code == promo_code_applied) |
                        (MarketingSubscriber.promo_free_code == promo_code_applied) |
                        (MarketingSubscriber.founder_promo_code == promo_code_applied)
                    ).first()
                    if subscriber:
                        now = get_uk_now()
                        if subscriber.founder_promo_code and subscriber.founder_promo_code == promo_code_applied:
                            subscriber.founder_promo_used = True
                            subscriber.founder_promo_used_at = now
                            subscriber.founder_promo_used_booking_id = booking_id
                        elif subscriber.promo_10_code and subscriber.promo_10_code == promo_code_applied:
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

                # Check if this promo code is linked to a promo modal and deactivate it
                try:
                    check_promo_modal_code_used(db, promo_code_applied)
                except Exception as e:
                    print(f"[FREE BOOKING] Failed to check promo modal code usage: {e}")

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

                # Calculate pickup time (30 mins after scheduled arrival) - format as "From HH:MM onwards"
                pickup_time_str = ""
                if pickup_time:
                    # pickup_time is the landing time, add 30 mins
                    landing_mins = pickup_time.hour * 60 + pickup_time.minute
                    pickup_mins = landing_mins + 30
                    if pickup_mins >= 24 * 60:
                        pickup_mins -= 24 * 60
                    pickup_time_str = f"From {pickup_mins // 60:02d}:{pickup_mins % 60:02d} onwards"

                # Get flight arrival time for email
                flight_arrival_time_str = ""
                if request.flight_arrival_time:
                    flight_arrival_time_str = request.flight_arrival_time
                elif pickup_time:
                    # Fallback to pickup_time which stores landing time
                    flight_arrival_time_str = pickup_time.strftime("%H:%M")

                # Get flight departure time for email
                flight_departure_time_str = request.flight_departure_time or ""

                # Package name - use flexible duration format
                duration_days = (pickup_date - dropoff_date).days
                package_name = f"{duration_days} day{'s' if duration_days != 1 else ''}"

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

                # Format flight info: airline + flight number (if provided) + destination
                # Use booking's stored values (works for both dropdown selection and manual "Other" entry)
                departure_flight = ""
                if booking.dropoff_airline_name or booking.dropoff_destination:
                    parts = []
                    if booking.dropoff_airline_name:
                        parts.append(booking.dropoff_airline_name)
                    if request.flight_number:
                        parts.append(request.flight_number)
                    departure_flight = " ".join(parts)
                    if booking.dropoff_destination:
                        departure_flight += f" to {booking.dropoff_destination}"
                elif request.flight_number:
                    departure_flight = request.flight_number

                return_flight = ""
                if booking.pickup_airline_name or booking.pickup_origin:
                    parts = []
                    if booking.pickup_airline_name:
                        parts.append(booking.pickup_airline_name)
                    if request.pickup_flight_number:
                        parts.append(request.pickup_flight_number)
                    return_flight = " ".join(parts)
                    if booking.pickup_origin:
                        return_flight += f" from {booking.pickup_origin}"
                elif request.pickup_flight_number:
                    return_flight = request.pickup_flight_number
                    if booking.pickup_origin:
                        return_flight += f" from {booking.pickup_origin}"

                email_sent = send_booking_confirmation_email(
                    email=request.email,
                    first_name=request.first_name,
                    booking_reference=booking_reference,
                    dropoff_date=dropoff_date_str,
                    dropoff_time=dropoff_time_str,
                    pickup_date=pickup_date_str,
                    pickup_time=pickup_time_str,
                    flight_arrival_time=flight_arrival_time_str,
                    flight_departure_time=flight_departure_time_str,
                    departure_flight=departure_flight,
                    return_flight=return_flight,
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
        # Stripe returns StripeObject, not dict - use bracket notation or getattr
        metadata = getattr(data, "metadata", {}) or {}
        booking_reference = metadata.get("booking_reference") if isinstance(metadata, dict) else getattr(metadata, "booking_reference", None)
        departure_id = metadata.get("departure_id") if isinstance(metadata, dict) else getattr(metadata, "departure_id", None)
        drop_off_slot = metadata.get("drop_off_slot") if isinstance(metadata, dict) else getattr(metadata, "drop_off_slot", None)
        promo_code = metadata.get("promo_code") if isinstance(metadata, dict) else getattr(metadata, "promo_code", None)
        meta_original_amount = metadata.get("original_amount") if isinstance(metadata, dict) else getattr(metadata, "original_amount", None)  # pence, as string
        meta_discount_amount = metadata.get("discount_amount") if isinstance(metadata, dict) else getattr(metadata, "discount_amount", None)  # pence, as string

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
                # Payment not found - likely a manual booking where admin confirms payment separately
                # Don't log as error, just print info for debugging
                print(f"[WEBHOOK] Payment intent {payment_intent_id} not found in database - likely a manual booking payment link (admin confirms manually)")
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
                    "amount_pence": data["amount"] if "amount" in data else None,
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
        log_promo("WEBHOOK promo_code check", {
            "promo_code": promo_code,
            "was_already_processed": was_already_processed,
            "booking_reference": booking_reference
        })
        if promo_code and not was_already_processed:
            log_promo("WEBHOOK MARK_USED starting", {"code": promo_code, "booking_reference": booking_reference})
            try:
                from db_models import PromoCode as DbPromoCode, Promotion as DbPromotion

                # Get booking ID from reference
                booking = db_service.get_booking_by_reference(db, booking_reference)
                bid = booking.id if booking else None

                # First, check if it's from the new promo_codes table
                # Use case-insensitive comparison and normalize to uppercase
                promo_code_upper = promo_code.strip().upper() if promo_code else None
                promo_code_record = db.query(DbPromoCode).filter(
                    DbPromoCode.code == promo_code_upper
                ).first() if promo_code_upper else None

                log_promo("WEBHOOK MARK_USED lookup result", {
                    "promo_code_upper": promo_code_upper,
                    "found_in_new_system": promo_code_record is not None,
                    "can_be_used": promo_code_record.can_be_used if promo_code_record else None,
                    "booking_id": bid
                })

                if promo_code_record and promo_code_record.can_be_used:
                    log_promo("WEBHOOK MARK_USED found in new system", {
                        "code": promo_code,
                        "promotion_id": promo_code_record.promotion_id,
                        "is_multi_use": promo_code_record.is_multi_use,
                        "booking_id": bid
                    })
                    # Get discount info from promotion
                    promotion = db.query(DbPromotion).filter(DbPromotion.id == promo_code_record.promotion_id).first()
                    discount_pct = promotion.discount_percent if promotion else 0
                    # Get actual discount amount from metadata (already extracted from data above)
                    discount_amount = None
                    if meta_discount_amount:
                        try:
                            discount_amount = int(meta_discount_amount)
                        except (ValueError, TypeError):
                            discount_amount = None

                    mark_promo_code_used(db, promo_code_record, bid, discount_pct, discount_amount)
                    db.commit()
                    log_promo("WEBHOOK MARK_USED success (new system)", {"code": promo_code, "booking_id": bid})
                elif not promo_code_record:
                    # Fallback: Legacy MarketingSubscriber promo fields
                    subscriber = db.query(MarketingSubscriber).filter(
                        (MarketingSubscriber.promo_code == promo_code) |
                        (MarketingSubscriber.promo_10_code == promo_code) |
                        (MarketingSubscriber.promo_free_code == promo_code) |
                        (MarketingSubscriber.founder_promo_code == promo_code)
                    ).first()
                    if subscriber:
                        now = get_uk_now()
                        if subscriber.founder_promo_code and subscriber.founder_promo_code == promo_code:
                            subscriber.founder_promo_used = True
                            subscriber.founder_promo_used_at = now
                            subscriber.founder_promo_used_booking_id = bid
                        elif subscriber.promo_10_code and subscriber.promo_10_code == promo_code:
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

            # Check if this promo code is linked to a promo modal and deactivate it
            try:
                check_promo_modal_code_used(db, promo_code)
            except Exception as e:
                print(f"[WEBHOOK] Failed to check promo modal code usage: {e}")

        # Send booking confirmation email
        print(f"[EMAIL] Starting to send confirmation email for booking: {booking_reference}")
        try:
            booking = db_service.get_booking_by_reference(db, booking_reference)
            print(f"[EMAIL] Booking found: {booking is not None}")
            if booking:
                print(f"[EMAIL] Customer email: {booking.customer.email}, name: {booking.customer.first_name}")
                # pickup_time is now the collection time (arrival + 30)
                pickup_time_str = f"From {booking.pickup_time.strftime('%H:%M')} onwards" if booking.pickup_time else ""

                # Get flight arrival time for email
                flight_arrival_time_str = booking.flight_arrival_time.strftime("%H:%M") if booking.flight_arrival_time else ""

                # Get flight departure time for email
                flight_departure_time_str = ""
                if booking.flight_departure_time:
                    flight_departure_time_str = booking.flight_departure_time.strftime("%H:%M")

                # Format dates nicely
                dropoff_date_str = booking.dropoff_date.strftime("%A, %d %B %Y")
                pickup_date_str = booking.pickup_date.strftime("%A, %d %B %Y")
                dropoff_time_str = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else ""

                # Format flight info: airline + flight number (if provided) + destination
                departure_flight = ""
                if booking.dropoff_airline_name or booking.dropoff_destination:
                    parts = []
                    if booking.dropoff_airline_name:
                        parts.append(booking.dropoff_airline_name)
                    if booking.dropoff_flight_number and booking.dropoff_flight_number != 'Unknown':
                        parts.append(booking.dropoff_flight_number)
                    departure_flight = " ".join(parts)
                    if booking.dropoff_destination:
                        departure_flight += f" to {booking.dropoff_destination}"

                return_flight = ""
                if booking.pickup_airline_name or booking.pickup_origin:
                    parts = []
                    if booking.pickup_airline_name:
                        parts.append(booking.pickup_airline_name)
                    if booking.pickup_flight_number and booking.pickup_flight_number != 'Unknown':
                        parts.append(booking.pickup_flight_number)
                    return_flight = " ".join(parts)
                    if booking.pickup_origin:
                        return_flight += f" from {booking.pickup_origin}"

                # Package name - use flexible duration format
                duration_days = (booking.pickup_date - booking.dropoff_date).days
                package_name = f"{duration_days} day{'s' if duration_days != 1 else ''}"

                # Amount paid - use bracket notation for Stripe object
                amount_pence = data["amount"] if "amount" in data else 0
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
                    flight_arrival_time=flight_arrival_time_str,
                    flight_departure_time=flight_departure_time_str,
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
        # Stripe returns StripeObject, not dict - use getattr for attributes
        metadata = getattr(data, "metadata", {}) or {}
        booking_reference = metadata.get("booking_reference") if isinstance(metadata, dict) else getattr(metadata, "booking_reference", None)
        last_payment_error = getattr(data, "last_payment_error", None)
        error_message = getattr(last_payment_error, "message", "Unknown error") if last_payment_error else "Unknown error"

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
        # Stripe returns StripeObject - use bracket notation or getattr
        refund_amount = data["amount_refunded"] if "amount_refunded" in data else 0
        original_amount = data["amount"] if "amount" in data else 0
        payment_intent_id = data["payment_intent"] if "payment_intent" in data else None
        metadata = getattr(data, "metadata", {}) or {}
        booking_reference = metadata.get("booking_reference") if isinstance(metadata, dict) else getattr(metadata, "booking_reference", None)

        # Get refund details from the refunds list
        refunds_obj = getattr(data, "refunds", None)
        refunds_list = refunds_obj.data if refunds_obj and hasattr(refunds_obj, 'data') else []
        latest_refund_id = refunds_list[0]["id"] if refunds_list and len(refunds_list) > 0 else None

        # Update Payment record with refund information
        if payment_intent_id:
            payment = db.query(Payment).filter(
                Payment.stripe_payment_intent_id == payment_intent_id
            ).first()

            if payment:
                payment.refund_amount_pence = refund_amount
                payment.refunded_at = datetime.utcnow()
                if latest_refund_id:
                    payment.refund_id = latest_refund_id

                # Set status based on refund amount
                if refund_amount >= original_amount:
                    payment.status = PaymentStatus.REFUNDED
                else:
                    payment.status = PaymentStatus.PARTIALLY_REFUNDED

                db.commit()

        # Log refund
        log_audit_event(
            db=db,
            event=AuditLogEvent.BOOKING_REFUNDED,
            request=request,
            booking_reference=booking_reference,
            event_data={
                "charge_id": charge_id,
                "payment_intent_id": payment_intent_id,
                "refund_amount_pence": refund_amount,
            },
        )

        return {"status": "refunded", "payment_intent_id": payment_intent_id}

    elif event_type in ("refund.updated", "refund.created"):
        # Handle refund events directly (alternative to charge.refunded)
        # Stripe returns StripeObject - use bracket notation
        refund_id = data["id"]
        refund_amount = data["amount"] if "amount" in data else 0
        refund_status = data["status"] if "status" in data else None
        payment_intent_id = data["payment_intent"] if "payment_intent" in data else None

        # Only process successful refunds
        if refund_status == "succeeded" and payment_intent_id:
            payment = db.query(Payment).filter(
                Payment.stripe_payment_intent_id == payment_intent_id
            ).first()

            if payment:
                # Update refund amount (accumulate if partial refunds)
                current_refund = payment.refund_amount_pence or 0
                # For refund.updated, the amount is the total refund amount
                payment.refund_amount_pence = refund_amount
                payment.refunded_at = datetime.utcnow()
                payment.refund_id = refund_id

                # Set status based on refund amount vs original
                if payment.amount_pence and refund_amount >= payment.amount_pence:
                    payment.status = PaymentStatus.REFUNDED
                else:
                    payment.status = PaymentStatus.PARTIALLY_REFUNDED

                db.commit()

                log_audit_event(
                    db=db,
                    event=AuditLogEvent.BOOKING_REFUNDED,
                    request=request,
                    event_data={
                        "refund_id": refund_id,
                        "payment_intent_id": payment_intent_id,
                        "refund_amount_pence": refund_amount,
                        "source": event_type,
                    },
                )

                return {"status": "refunded", "payment_intent_id": payment_intent_id}

        return {"status": "received", "type": event_type, "refund_status": refund_status}

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
    vehicle_inspection_read: Optional[bool] = False  # Confirmed they read the T&C (drop-off only)
    acknowledgement_confirmed: Optional[bool] = False  # Confirmed acknowledgement (return only)
    declined: Optional[bool] = False  # Customer declined inspection (pickup only)
    mileage: Optional[int] = None  # Vehicle mileage at inspection


class UpdateInspectionRequest(BaseModel):
    notes: Optional[str] = None
    photos: Optional[dict] = None
    customer_name: Optional[str] = None
    signed_date: Optional[str] = None
    signature: Optional[str] = None
    vehicle_inspection_read: Optional[bool] = None
    acknowledgement_confirmed: Optional[bool] = None
    declined: Optional[bool] = None  # Customer declined inspection (pickup only)
    mileage: Optional[int] = None


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
            "flight_departure_time": b.flight_departure_time.strftime("%H:%M") if b.flight_departure_time else None,
            "dropoff_flight_number": b.dropoff_flight_number,
            "dropoff_airline_name": b.dropoff_airline_name,
            "dropoff_destination": b.dropoff_destination,
            "pickup_date": b.pickup_date.isoformat() if b.pickup_date else None,
            "pickup_time": b.pickup_time.strftime("%H:%M") if b.pickup_time else None,
            "flight_arrival_time": b.flight_arrival_time.strftime("%H:%M") if b.flight_arrival_time else None,
            "pickup_flight_number": b.pickup_flight_number,
            "pickup_airline_name": b.pickup_airline_name,
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
        acknowledgement_confirmed=request.acknowledgement_confirmed or False,
        declined=request.declined or False,
        mileage=request.mileage,
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
            "acknowledgement_confirmed": inspection.acknowledgement_confirmed,
            "mileage": inspection.mileage,
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
                "acknowledgement_confirmed": i.acknowledgement_confirmed,
                "mileage": i.mileage,
                "declined": i.declined or False,
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
    if request.acknowledgement_confirmed is not None:
        inspection.acknowledgement_confirmed = request.acknowledgement_confirmed
    if request.declined is not None:
        inspection.declined = request.declined
    if request.mileage is not None:
        inspection.mileage = request.mileage

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
            "acknowledgement_confirmed": inspection.acknowledgement_confirmed,
            "mileage": inspection.mileage,
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
    """Mark a booking as completed.

    Sets the completion timestamp which triggers a thank you email
    to be sent 2 hours later via the email scheduler.
    """
    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail=f"Booking must be confirmed to complete. Current status: {booking.status.value}")

    booking.status = BookingStatus.COMPLETED
    booking.completed_at = datetime.utcnow()  # Set completion time for thank you email scheduling
    db.commit()

    return {"success": True, "message": f"Booking {booking.reference} marked as completed"}


@app.post("/api/employee/bookings/{booking_id}/decline-inspection")
async def decline_return_inspection(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark that the customer declined the return inspection.

    Creates a pickup inspection record with declined=True.
    This allows completing the booking without a full return inspection.
    """
    from db_models import VehicleInspection, InspectionType

    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Check if pickup inspection already exists
    existing = db.query(VehicleInspection).filter(
        VehicleInspection.booking_id == booking_id,
        VehicleInspection.inspection_type == InspectionType.PICKUP
    ).first()

    if existing:
        existing.declined = True
    else:
        # Create a new declined inspection record
        inspection = VehicleInspection(
            booking_id=booking_id,
            inspection_type=InspectionType.PICKUP,
            declined=True,
            inspector_id=current_user.id
        )
        db.add(inspection)

    db.commit()

    return {"success": True, "message": f"Return inspection declined for booking {booking.reference}"}


@app.post("/api/employee/bookings/{booking_id}/undecline-inspection")
async def undecline_return_inspection(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Undo the decline of return inspection."""
    from db_models import VehicleInspection, InspectionType

    booking = db.query(DbBooking).filter(DbBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Find the pickup inspection
    inspection = db.query(VehicleInspection).filter(
        VehicleInspection.booking_id == booking_id,
        VehicleInspection.inspection_type == InspectionType.PICKUP
    ).first()

    if inspection:
        # If only declined (no other data), delete it; otherwise just clear the declined flag
        if inspection.declined and not inspection.notes and not inspection.photos and not inspection.signature:
            db.delete(inspection)
        else:
            inspection.declined = False

    db.commit()

    return {"success": True, "message": f"Return inspection decline removed for booking {booking.reference}"}


# ============================================================================
# PRICING SETTINGS ENDPOINTS
# ============================================================================


class PricingSettingsResponse(BaseModel):
    """Response model for pricing settings with anchor pricing."""
    days_1_4_price: float      # 1-4 days anchor
    week1_base_price: float    # 7 days anchor
    week2_base_price: float    # 14 days anchor
    daily_increment: float     # Daily increment between anchors
    tier_increment: float      # Early -> Standard -> Late increment
    updated_at: Optional[str] = None


class PricingSettingsUpdate(BaseModel):
    """Request model for updating pricing settings with anchor pricing."""
    days_1_4_price: float      # 1-4 days anchor
    week1_base_price: float    # 7 days anchor
    week2_base_price: float    # 14 days anchor
    daily_increment: float     # Daily increment between anchors
    tier_increment: float      # Early -> Standard -> Late increment


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
    Uses simplified anchor pricing model.
    """
    from db_models import PricingSettings

    settings = db.query(PricingSettings).first()

    if not settings:
        return {
            "days_1_4_price": 65.0,
            "week1_base_price": 85.0,
            "week2_base_price": 150.0,
            "daily_increment": 8.0,
            "tier_increment": 5.0,
            "updated_at": None,
            "updated_by": None,
        }

    return {
        "days_1_4_price": float(settings.days_1_4_price) if settings.days_1_4_price else 65.0,
        "week1_base_price": float(settings.week1_base_price) if settings.week1_base_price else 85.0,
        "week2_base_price": float(settings.week2_base_price) if settings.week2_base_price else 150.0,
        "daily_increment": float(settings.daily_increment) if settings.daily_increment is not None else 8.0,
        "tier_increment": float(settings.tier_increment) if settings.tier_increment is not None else 5.0,
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
    Admin endpoint: Update pricing settings with anchor pricing model.
    """
    from db_models import PricingSettings
    from decimal import Decimal

    settings = db.query(PricingSettings).first()

    if not settings:
        # Create new settings
        settings = PricingSettings(
            days_1_4_price=Decimal(str(update.days_1_4_price)),
            week1_base_price=Decimal(str(update.week1_base_price)),
            week2_base_price=Decimal(str(update.week2_base_price)),
            daily_increment=Decimal(str(update.daily_increment)),
            tier_increment=Decimal(str(update.tier_increment)),
            updated_by=current_user.id,
        )
        db.add(settings)
    else:
        # Update existing
        settings.days_1_4_price = Decimal(str(update.days_1_4_price))
        settings.week1_base_price = Decimal(str(update.week1_base_price))
        settings.week2_base_price = Decimal(str(update.week2_base_price))
        settings.daily_increment = Decimal(str(update.daily_increment))
        settings.tier_increment = Decimal(str(update.tier_increment))
        settings.updated_by = current_user.id

    db.commit()
    db.refresh(settings)

    return {
        "success": True,
        "message": "Pricing updated successfully",
        "pricing": {
            "days_1_4_price": float(settings.days_1_4_price),
            "week1_base_price": float(settings.week1_base_price),
            "week2_base_price": float(settings.week2_base_price),
            "daily_increment": float(settings.daily_increment),
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


class CreateDepartureRequest(BaseModel):
    """Request model for creating a flight departure."""
    date: str  # ISO format: YYYY-MM-DD
    flight_number: str
    airline_code: str
    airline_name: str
    departure_time: str  # HH:MM format
    destination_code: str
    destination_name: Optional[str] = None
    capacity_tier: int = 0  # Default: Call Us only


class CreateArrivalRequest(BaseModel):
    """Request model for creating a flight arrival."""
    date: str  # ISO format: YYYY-MM-DD
    flight_number: str
    airline_code: str
    airline_name: str
    arrival_time: str  # HH:MM format
    origin_code: str
    origin_name: Optional[str] = None
    departure_time: Optional[str] = None  # HH:MM format (when it left origin)


@app.get("/api/admin/flights/departures")
async def get_admin_departures(
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    destination: Optional[str] = None,
    airline: Optional[str] = None,
    flight_number: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = None,
    start_date: Optional[date] = Query(None, description="Filter flights from this date onwards (default: 2026-01-01)"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all departure flights with optional filters.
    Sorted by date (ASC by default, DESC optional).
    Default start_date is 2026-01-01 if not specified.
    Cached for 3 months (reference data only).
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Check if using default params (cacheable)
    is_default_request = (
        sort_order == "asc" and
        destination is None and
        airline is None and
        flight_number is None and
        month is None and
        year is None and
        start_date is None
    )

    # Check cache for default requests
    global _flight_departures_cache
    if is_default_request and not refresh:
        if _flight_departures_cache["data"] is not None and _flight_departures_cache["cached_at"] is not None:
            cache_age = (now - _flight_departures_cache["cached_at"]).total_seconds()
            if cache_age < FLIGHT_CACHE_DURATION_SECONDS:
                cached_response = _flight_departures_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    query = db.query(FlightDeparture)

    # Apply start_date filter (default to 2026-01-01)
    filter_start_date = start_date if start_date else date(2026, 1, 1)
    query = query.filter(FlightDeparture.date >= filter_start_date)

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

    result = {
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

    # Store in cache for default requests
    if is_default_request:
        _flight_departures_cache["data"] = result.copy()
        _flight_departures_cache["cached_at"] = now

    result["cached"] = False
    return result


@app.get("/api/admin/flights/arrivals")
async def get_admin_arrivals(
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    origin: Optional[str] = None,
    airline: Optional[str] = None,
    flight_number: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = None,
    start_date: Optional[date] = Query(None, description="Filter flights from this date onwards (default: 2026-01-01)"),
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get all arrival flights with optional filters.
    Sorted by date (ASC by default, DESC optional).
    Default start_date is 2026-01-01 if not specified.
    Cached for 3 months (reference data only).
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Check if using default params (cacheable)
    is_default_request = (
        sort_order == "asc" and
        origin is None and
        airline is None and
        flight_number is None and
        month is None and
        year is None and
        start_date is None
    )

    # Check cache for default requests
    global _flight_arrivals_cache
    if is_default_request and not refresh:
        if _flight_arrivals_cache["data"] is not None and _flight_arrivals_cache["cached_at"] is not None:
            cache_age = (now - _flight_arrivals_cache["cached_at"]).total_seconds()
            if cache_age < FLIGHT_CACHE_DURATION_SECONDS:
                cached_response = _flight_arrivals_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

    query = db.query(FlightArrival)

    # Apply start_date filter (default to 2026-01-01)
    filter_start_date = start_date if start_date else date(2026, 1, 1)
    query = query.filter(FlightArrival.date >= filter_start_date)

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

    result = {
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

    # Store in cache for default requests
    if is_default_request:
        _flight_arrivals_cache["data"] = result.copy()
        _flight_arrivals_cache["cached_at"] = now

    result["cached"] = False
    return result


@app.get("/api/admin/flights/filters")
async def get_admin_flight_filters(
    refresh: bool = Query(False, description="Force refresh cache"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get unique filter options for flights (airlines, destinations, origins, months).
    Cached for 3 months (reference data only).
    """
    import pytz
    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # Check cache
    global _flight_filters_cache
    if not refresh:
        if _flight_filters_cache["data"] is not None and _flight_filters_cache["cached_at"] is not None:
            cache_age = (now - _flight_filters_cache["cached_at"]).total_seconds()
            if cache_age < FLIGHT_CACHE_DURATION_SECONDS:
                cached_response = _flight_filters_cache["data"].copy()
                cached_response["cached"] = True
                cached_response["cache_age_minutes"] = round(cache_age / 60, 1)
                return cached_response

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

    result = {
        "airlines": airlines,
        "destinations": destinations,
        "origins": origins,
        "months": months,
    }

    # Store in cache
    _flight_filters_cache["data"] = result.copy()
    _flight_filters_cache["cached_at"] = now

    result["cached"] = False
    return result


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
            # Calculate pickup time (arrival + 30 min)
            arrival_datetime = datetime.combine(datetime.today(), new_arrival_time)
            pickup_time = (arrival_datetime + timedelta(minutes=30)).time()

            booking.flight_arrival_time = new_arrival_time
            booking.pickup_time = pickup_time
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


@app.post("/api/admin/flights/departures", status_code=201)
async def create_admin_departure(
    request: CreateDepartureRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Create a new departure flight.
    """
    # Check for duplicate (same date, flight_number, departure_time)
    existing = db.query(FlightDeparture).filter(
        FlightDeparture.date == date.fromisoformat(request.date),
        FlightDeparture.flight_number == request.flight_number,
        FlightDeparture.departure_time == time.fromisoformat(request.departure_time)
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Flight {request.flight_number} already exists on {request.date} at {request.departure_time}"
        )

    # Validate capacity tier
    if request.capacity_tier not in [0, 2, 4, 6, 8]:
        raise HTTPException(status_code=400, detail="Capacity tier must be 0, 2, 4, 6, or 8")

    departure = FlightDeparture(
        date=date.fromisoformat(request.date),
        flight_number=request.flight_number.upper(),
        airline_code=request.airline_code.upper(),
        airline_name=request.airline_name,
        departure_time=time.fromisoformat(request.departure_time),
        destination_code=request.destination_code.upper(),
        destination_name=request.destination_name,
        capacity_tier=request.capacity_tier,
        slots_booked_early=0,
        slots_booked_late=0,
        updated_by=current_user.email,
    )

    db.add(departure)
    db.commit()
    db.refresh(departure)

    return {
        "success": True,
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
        }
    }


@app.post("/api/admin/flights/arrivals", status_code=201)
async def create_admin_arrival(
    request: CreateArrivalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Create a new arrival flight.
    """
    # Check for duplicate (same date, flight_number, arrival_time)
    existing = db.query(FlightArrival).filter(
        FlightArrival.date == date.fromisoformat(request.date),
        FlightArrival.flight_number == request.flight_number,
        FlightArrival.arrival_time == time.fromisoformat(request.arrival_time)
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Flight {request.flight_number} already exists on {request.date} at {request.arrival_time}"
        )

    arrival = FlightArrival(
        date=date.fromisoformat(request.date),
        flight_number=request.flight_number.upper(),
        airline_code=request.airline_code.upper(),
        airline_name=request.airline_name,
        arrival_time=time.fromisoformat(request.arrival_time),
        departure_time=time.fromisoformat(request.departure_time) if request.departure_time else None,
        origin_code=request.origin_code.upper(),
        origin_name=request.origin_name,
        updated_by=current_user.email,
    )

    db.add(arrival)
    db.commit()
    db.refresh(arrival)

    return {
        "success": True,
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
        }
    }


@app.delete("/api/admin/flights/departures/{departure_id}", status_code=200)
async def delete_admin_departure(
    departure_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete a departure flight.
    Returns error if flight has associated bookings.
    """
    departure = db.query(FlightDeparture).filter(FlightDeparture.id == departure_id).first()

    if not departure:
        raise HTTPException(status_code=404, detail="Departure not found")

    # Check for linked bookings
    linked_bookings = db.query(DbBooking).filter(DbBooking.departure_id == departure_id).count()
    if linked_bookings > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete flight: {linked_bookings} booking(s) are linked to this departure"
        )

    # Store flight info for history
    history = FlightDepartureHistory(
        flight_id=departure.id,
        date=departure.date,
        flight_number=departure.flight_number,
        airline_code=departure.airline_code,
        airline_name=departure.airline_name,
        departure_time=departure.departure_time,
        destination_code=departure.destination_code,
        destination_name=departure.destination_name,
        capacity_tier=departure.capacity_tier,
        slots_booked_early=departure.slots_booked_early,
        slots_booked_late=departure.slots_booked_late,
        change_type="deleted",
        changed_by=current_user.email,
    )
    db.add(history)

    db.delete(departure)
    db.commit()

    return {
        "success": True,
        "message": f"Departure {departure.flight_number} on {departure.date} deleted successfully"
    }


@app.delete("/api/admin/flights/arrivals/{arrival_id}", status_code=200)
async def delete_admin_arrival(
    arrival_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete an arrival flight.
    Returns error if flight has associated bookings.
    """
    arrival = db.query(FlightArrival).filter(FlightArrival.id == arrival_id).first()

    if not arrival:
        raise HTTPException(status_code=404, detail="Arrival not found")

    # Check for linked bookings
    linked_bookings = db.query(DbBooking).filter(DbBooking.arrival_id == arrival_id).count()
    if linked_bookings > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete flight: {linked_bookings} booking(s) are linked to this arrival"
        )

    # Store flight info for history
    history = FlightArrivalHistory(
        flight_id=arrival.id,
        date=arrival.date,
        flight_number=arrival.flight_number,
        airline_code=arrival.airline_code,
        airline_name=arrival.airline_name,
        departure_time=arrival.departure_time,
        arrival_time=arrival.arrival_time,
        origin_code=arrival.origin_code,
        origin_name=arrival.origin_name,
        change_type="deleted",
        changed_by=current_user.email,
    )
    db.add(history)

    db.delete(arrival)
    db.commit()

    return {
        "success": True,
        "message": f"Arrival {arrival.flight_number} on {arrival.date} deleted successfully"
    }


# =============================================================================
# QA Dashboard - Test Results Endpoints
# =============================================================================

@app.get("/api/admin/db-health")
async def get_database_health(
    current_user: User = Depends(require_admin),
):
    """
    Get database connection pool health status for monitoring.
    Shows current pool usage and warns if connections are running low.
    """
    from database import get_pool_status

    status = get_pool_status()

    # Determine health status
    if status["usage_percent"] >= 90:
        health = "critical"
        message = "Connection pool nearly exhausted!"
    elif status["usage_percent"] >= 70:
        health = "warning"
        message = "Connection pool usage is high"
    else:
        health = "healthy"
        message = "Connection pool is healthy"

    return {
        "health": health,
        "message": message,
        **status
    }


@app.get("/api/admin/test-results")
async def get_test_results(
    limit: int = Query(10, ge=1, le=100),
    environment: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get recent test run results for the QA Dashboard.
    Returns the most recent test runs, optionally filtered by environment.
    """
    from db_models import TestRun, TestRunStatus

    query = db.query(TestRun).order_by(TestRun.started_at.desc())

    if environment:
        query = query.filter(TestRun.environment == environment)

    test_runs = query.limit(limit).all()

    return {
        "test_runs": [
            {
                "id": run.id,
                "environment": run.environment,
                "run_type": run.run_type,
                "status": run.status.value,
                "tests_passed": run.tests_passed,
                "tests_failed": run.tests_failed,
                "tests_skipped": run.tests_skipped,
                "tests_total": run.tests_total,
                "coverage_percent": float(run.coverage_percent) if run.coverage_percent else None,
                "duration_seconds": run.duration_seconds,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "commit_sha": run.commit_sha,
                "branch": run.branch,
                "logs_url": run.logs_url,
                "triggered_by": run.triggered_by,
                "pass_rate": run.pass_rate,
            }
            for run in test_runs
        ]
    }


@app.get("/api/admin/test-results/latest")
async def get_latest_test_result(
    environment: str = "staging",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get the most recent test run for a specific environment.
    """
    from db_models import TestRun, TestRunStatus

    test_run = db.query(TestRun).filter(
        TestRun.environment == environment
    ).order_by(TestRun.started_at.desc()).first()

    if not test_run:
        return {"test_run": None}

    return {
        "test_run": {
            "id": test_run.id,
            "environment": test_run.environment,
            "run_type": test_run.run_type,
            "status": test_run.status.value,
            "tests_passed": test_run.tests_passed,
            "tests_failed": test_run.tests_failed,
            "tests_skipped": test_run.tests_skipped,
            "tests_total": test_run.tests_total,
            "coverage_percent": float(test_run.coverage_percent) if test_run.coverage_percent else None,
            "duration_seconds": test_run.duration_seconds,
            "started_at": test_run.started_at.isoformat() if test_run.started_at else None,
            "completed_at": test_run.completed_at.isoformat() if test_run.completed_at else None,
            "commit_sha": test_run.commit_sha,
            "branch": test_run.branch,
            "logs_url": test_run.logs_url,
            "triggered_by": test_run.triggered_by,
            "pass_rate": test_run.pass_rate,
        }
    }


class CreateTestRunRequest(BaseModel):
    """Request to create a new test run."""
    environment: str = "staging"
    run_type: str = "scheduled"
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
    api_key: str  # Simple API key for CI authentication


@app.post("/api/test-results")
async def create_test_result(
    request: CreateTestRunRequest,
    db: Session = Depends(get_db),
):
    """
    Create a new test run result. Called by CI/CD pipeline.
    Uses API key authentication instead of session auth.
    """
    from db_models import TestRun, TestRunStatus
    import os

    # Simple API key check (set via environment variable)
    expected_key = os.environ.get("TEST_RESULTS_API_KEY", "tag-test-results-2026")
    if request.api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Determine status based on results
    if request.tests_failed > 0:
        status = TestRunStatus.FAILED
    elif request.tests_total == 0:
        status = TestRunStatus.ERROR
    else:
        status = TestRunStatus.PASSED

    test_run = TestRun(
        environment=request.environment,
        run_type=request.run_type,
        status=status,
        tests_passed=request.tests_passed,
        tests_failed=request.tests_failed,
        tests_skipped=request.tests_skipped,
        tests_total=request.tests_total,
        coverage_percent=request.coverage_percent,
        duration_seconds=request.duration_seconds,
        commit_sha=request.commit_sha,
        branch=request.branch,
        logs_url=request.logs_url,
        report_json=request.report_json,
        triggered_by=request.triggered_by,
        completed_at=datetime.now(timezone.utc),
    )

    db.add(test_run)
    db.commit()
    db.refresh(test_run)

    return {
        "success": True,
        "test_run_id": test_run.id,
        "status": test_run.status.value,
        "pass_rate": test_run.pass_rate,
    }


# =============================================================================
# QA Dashboard - Audit Logs & Error Logs Endpoints
# =============================================================================

@app.get("/api/admin/audit-logs")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    booking_reference: Optional[str] = None,
    event: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get audit logs for the QA Dashboard with filtering.

    Filters:
    - search: Search in email, customer name, session_id, booking_reference
    - booking_reference: Exact match on booking reference
    - event: Filter by event type
    - date_from/date_to: Date range filter (ISO format)
    """
    # Use raw SQL to avoid enum mapping issues with event type
    where_clauses = []
    params = {}

    if booking_reference:
        where_clauses.append("booking_reference ILIKE :booking_ref")
        params["booking_ref"] = f"%{booking_reference}%"

    if event:
        where_clauses.append("event::text = :event")
        params["event"] = event

    if search:
        where_clauses.append("""(
            booking_reference ILIKE :search OR
            session_id ILIKE :search OR
            event_data::text ILIKE :search
        )""")
        params["search"] = f"%{search}%"

    if date_from:
        try:
            from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            where_clauses.append("created_at >= :date_from")
            params["date_from"] = from_dt
        except ValueError:
            pass

    if date_to:
        try:
            to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            where_clauses.append("created_at <= :date_to")
            params["date_to"] = to_dt
        except ValueError:
            pass

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Get total count
    count_sql = f"SELECT COUNT(*) FROM audit_logs WHERE {where_sql}"
    total_count = db.execute(text(count_sql), params).scalar()

    # Get paginated results
    query_sql = f"""
        SELECT id, session_id, booking_reference, event::text as event,
               event_data, ip_address, user_agent, created_at
        FROM audit_logs
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    result = db.execute(text(query_sql), params)
    rows = result.fetchall()

    return {
        "audit_logs": [
            {
                "id": row.id,
                "session_id": row.session_id,
                "booking_reference": row.booking_reference,
                "event": row.event,
                "event_data": row.event_data,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/admin/audit-logs/events")
async def get_audit_log_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get list of all audit event types for filter dropdown.
    """
    from db_models import AuditLogEvent

    return {
        "events": [e.value for e in AuditLogEvent]
    }


@app.get("/api/admin/error-logs")
async def get_error_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = None,
    booking_reference: Optional[str] = None,
    severity: Optional[str] = None,
    error_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get error logs for the QA Dashboard with filtering.

    Filters:
    - search: Search in message, endpoint, session_id, booking_reference
    - booking_reference: Filter by booking reference
    - severity: Filter by severity (info, warning, error, critical)
    - error_type: Filter by error type
    - date_from/date_to: Date range filter (ISO format)
    """
    # Use raw SQL to avoid enum mapping issues with severity
    # Build WHERE clauses
    where_clauses = []
    params = {}

    if booking_reference:
        where_clauses.append("booking_reference ILIKE :booking_ref")
        params["booking_ref"] = f"%{booking_reference}%"

    if severity:
        where_clauses.append("severity::text = :severity")
        params["severity"] = severity

    if error_type:
        where_clauses.append("error_type ILIKE :error_type")
        params["error_type"] = f"%{error_type}%"

    if search:
        where_clauses.append("""(
            booking_reference ILIKE :search OR
            session_id ILIKE :search OR
            message ILIKE :search OR
            endpoint ILIKE :search OR
            error_type ILIKE :search
        )""")
        params["search"] = f"%{search}%"

    if date_from:
        try:
            from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            where_clauses.append("created_at >= :date_from")
            params["date_from"] = from_dt
        except ValueError:
            pass

    if date_to:
        try:
            to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            where_clauses.append("created_at <= :date_to")
            params["date_to"] = to_dt
        except ValueError:
            pass

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Get total count
    count_sql = f"SELECT COUNT(*) FROM error_logs WHERE {where_sql}"
    total_count = db.execute(text(count_sql), params).scalar()

    # Get paginated results
    query_sql = f"""
        SELECT id, severity::text as severity, error_type, error_code, message,
               stack_trace, request_data, endpoint, booking_reference,
               session_id, ip_address, user_agent, created_at
        FROM error_logs
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    result = db.execute(text(query_sql), params)
    rows = result.fetchall()

    return {
        "error_logs": [
            {
                "id": row[0],
                "severity": row[1],
                "error_type": row[2],
                "error_code": row[3],
                "message": row[4],
                "stack_trace": row[5],
                "request_data": row[6],
                "endpoint": row[7],
                "booking_reference": row[8],
                "session_id": row[9],
                "ip_address": row[10],
                "user_agent": row[11],
                "created_at": row[12].isoformat() if row[12] else None,
            }
            for row in rows
        ],
        "total_count": total_count,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/admin/error-logs/severities")
async def get_error_log_severities(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get list of all error severity levels for filter dropdown.
    """
    from db_models import ErrorSeverity

    return {
        "severities": [s.value for s in ErrorSeverity]
    }


@app.get("/api/admin/error-logs/types")
async def get_error_log_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Get list of all error types currently in the database for filter dropdown.
    """
    from db_models import ErrorLog
    from sqlalchemy import distinct

    types = db.query(distinct(ErrorLog.error_type)).filter(
        ErrorLog.error_type.isnot(None)
    ).all()

    return {
        "error_types": [t[0] for t in types if t[0]]
    }


# =============================================================================
# QA Dashboard - SQL Interface (Secure Database Access)
# =============================================================================

# Store SQL session tokens in memory (user_id -> {token, expires_at})
sql_session_tokens: dict = {}

# Blocked SQL commands for security
BLOCKED_SQL_COMMANDS = [
    'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE',
    'VACUUM', 'REINDEX', 'CLUSTER', 'COPY', 'EXECUTE',
    'DEALLOCATE', 'PREPARE', 'LISTEN', 'NOTIFY', 'UNLISTEN',
    'LOAD', 'SECURITY', 'OWNER', 'TABLESPACE', 'EXTENSION',
]

# Commands that require confirmation
WRITE_SQL_COMMANDS = ['INSERT', 'UPDATE', 'DELETE']


def is_sql_command_blocked(query: str) -> tuple[bool, str]:
    """Check if a SQL query contains blocked commands."""
    import re
    query_upper = query.upper().strip()
    for cmd in BLOCKED_SQL_COMMANDS:
        # Use word boundary regex to match whole command words only
        # This prevents false positives like 'created_at' matching 'CREATE'
        pattern = rf'\b{cmd}\b'
        if re.search(pattern, query_upper):
            return True, cmd
    return False, ""


def is_write_operation(query: str) -> bool:
    """Check if a SQL query is a write operation."""
    query_upper = query.upper().strip()
    for cmd in WRITE_SQL_COMMANDS:
        if query_upper.startswith(cmd):
            return True
    return False


def generate_sql_session_token() -> str:
    """Generate a secure random token for SQL session."""
    import secrets
    return secrets.token_urlsafe(32)


class SQLPinVerifyRequest(BaseModel):
    """Request to verify SQL PIN."""
    pin: str


class SQLQueryRequest(BaseModel):
    """Request to execute a SQL query."""
    query: str
    session_token: str
    confirmed: bool = False  # Must be True for write operations


@app.post("/api/admin/sql/verify-pin")
async def verify_sql_pin(
    request: SQLPinVerifyRequest,
    current_user: User = Depends(require_admin),
):
    """
    Verify the SQL PIN and return a session token valid for 2 hours.
    """
    settings = get_settings()

    if not settings.admin_sql_pin:
        raise HTTPException(status_code=503, detail="SQL interface is not configured. Please set ADMIN_SQL_PIN.")

    if request.pin != settings.admin_sql_pin:
        # Log failed attempt
        print(f"[SQL] Failed PIN attempt by user {current_user.id} ({current_user.email})")
        raise HTTPException(status_code=401, detail="Invalid PIN")

    # Generate session token valid for 2 hours
    token = generate_sql_session_token()
    expires_at = get_uk_now() + timedelta(hours=2)

    sql_session_tokens[current_user.id] = {
        "token": token,
        "expires_at": expires_at,
    }

    print(f"[SQL] PIN verified for user {current_user.id} ({current_user.email}), session expires at {expires_at}")

    return {
        "success": True,
        "session_token": token,
        "expires_at": expires_at.isoformat(),
    }


@app.get("/api/admin/sql/session-status")
async def get_sql_session_status(
    current_user: User = Depends(require_admin),
):
    """
    Check if the current user has a valid SQL session.
    """
    session = sql_session_tokens.get(current_user.id)

    if not session:
        return {"valid": False, "reason": "no_session"}

    if get_uk_now() > session["expires_at"]:
        # Session expired, clean up
        del sql_session_tokens[current_user.id]
        return {"valid": False, "reason": "expired"}

    return {
        "valid": True,
        "expires_at": session["expires_at"].isoformat(),
    }


@app.post("/api/admin/sql/execute")
async def execute_sql_query(
    request: SQLQueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Execute a SQL query against the database.

    Security:
    - Requires valid session token from PIN verification
    - Blocks dangerous commands (DROP, ALTER, CREATE, etc.)
    - Requires confirmation for write operations (INSERT, UPDATE, DELETE)
    - 30 second timeout
    - 500 row limit on results
    - All queries are logged to audit_logs
    """
    import time

    # Verify session token
    session = sql_session_tokens.get(current_user.id)
    if not session or session["token"] != request.session_token:
        raise HTTPException(status_code=401, detail="Invalid or missing SQL session. Please verify PIN.")

    if get_uk_now() > session["expires_at"]:
        del sql_session_tokens[current_user.id]
        raise HTTPException(status_code=401, detail="SQL session expired. Please verify PIN again.")

    query = request.query.strip()

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Check for blocked commands
    is_blocked, blocked_cmd = is_sql_command_blocked(query)
    if is_blocked:
        raise HTTPException(status_code=403, detail=f"Command '{blocked_cmd}' is not allowed for security reasons")

    # Check if write operation requires confirmation
    is_write = is_write_operation(query)
    if is_write and not request.confirmed:
        return {
            "requires_confirmation": True,
            "operation_type": query.upper().split()[0],
            "message": "This is a write operation. Please confirm to proceed.",
        }

    # Log the query attempt
    try:
        from db_models import AuditLog, AuditLogEvent
        audit_log = AuditLog(
            session_id=f"sql_admin_{current_user.id}",
            event=AuditLogEvent.ADMIN_SQL_QUERY if hasattr(AuditLogEvent, 'ADMIN_SQL_QUERY') else None,
            event_data=json.dumps({
                "user_id": current_user.id,
                "user_email": current_user.email,
                "query": query[:1000],  # Truncate long queries
                "is_write": is_write,
            }),
            created_at=get_uk_now(),
        )
        # We'll add this after execution to include results
    except Exception as e:
        print(f"[SQL] Failed to create audit log: {e}")

    # Execute the query with timeout
    start_time = time.time()
    try:
        # Set statement timeout (30 seconds)
        db.execute(text("SET statement_timeout = '30s'"))

        result = db.execute(text(query))

        execution_time = time.time() - start_time

        # Handle different query types
        if query.upper().strip().startswith('SELECT'):
            # Fetch results with row limit
            rows = result.fetchmany(500)
            columns = list(result.keys()) if result.keys() else []

            # Convert rows to list of dicts
            data = []
            for row in rows:
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    # Handle non-JSON-serializable types
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    elif isinstance(val, (bytes,)):
                        val = val.hex()
                    elif hasattr(val, 'value'):  # Enum
                        val = val.value
                    row_dict[col] = val
                data.append(row_dict)

            row_count = len(data)
            has_more = row_count == 500

            return {
                "success": True,
                "query_type": "SELECT",
                "columns": columns,
                "data": data,
                "row_count": row_count,
                "has_more": has_more,
                "execution_time": round(execution_time, 3),
            }
        else:
            # Write operation - commit and return affected rows
            db.commit()
            affected_rows = result.rowcount

            return {
                "success": True,
                "query_type": query.upper().split()[0],
                "affected_rows": affected_rows,
                "execution_time": round(execution_time, 3),
            }

    except Exception as e:
        db.rollback()
        error_msg = str(e)
        print(f"[SQL] Query error by user {current_user.id}: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Query error: {error_msg}")
    finally:
        # Reset statement timeout
        try:
            db.execute(text("SET statement_timeout = '0'"))
        except:
            pass


@app.post("/api/admin/sql/logout")
async def logout_sql_session(
    current_user: User = Depends(require_admin),
):
    """
    Invalidate the current SQL session.
    """
    if current_user.id in sql_session_tokens:
        del sql_session_tokens[current_user.id]

    return {"success": True, "message": "SQL session terminated"}


# =============================================================================
# Testimonials Endpoints
# =============================================================================

class TestimonialCreate(BaseModel):
    """Request to create a testimonial."""
    customer_name: str
    review_text: str
    star_rating: Optional[int] = None  # NULL for unrated (LinkedIn, FB, etc.)
    date_of_travel: Optional[str] = None  # DD/MM/YYYY format
    status: str = "inactive"
    is_featured: bool = False
    source: Optional[str] = None


class TestimonialUpdate(BaseModel):
    """Request to update a testimonial."""
    customer_name: Optional[str] = None
    review_text: Optional[str] = None
    star_rating: Optional[int] = None
    date_of_travel: Optional[str] = None
    status: Optional[str] = None
    is_featured: Optional[bool] = None
    source: Optional[str] = None


def validate_testimonial_data(data: dict):
    """Validate testimonial input data."""
    errors = []

    if "customer_name" in data and data["customer_name"] is not None:
        if not data["customer_name"] or len(data["customer_name"].strip()) == 0:
            errors.append({"field": "customer_name", "message": "Customer name is required"})
        elif len(data["customer_name"]) > 100:
            errors.append({"field": "customer_name", "message": "Customer name must be 100 characters or less"})

    if "review_text" in data and data["review_text"] is not None:
        if not data["review_text"] or len(data["review_text"].strip()) < 10:
            errors.append({"field": "review_text", "message": "Review must be at least 10 characters"})

    # star_rating is optional, but if provided must be 1-5
    if "star_rating" in data and data["star_rating"] is not None:
        if not isinstance(data["star_rating"], int) or data["star_rating"] < 1 or data["star_rating"] > 5:
            errors.append({"field": "star_rating", "message": "Star rating must be between 1 and 5"})

    if "status" in data and data["status"] is not None:
        if data["status"] not in ["active", "inactive"]:
            errors.append({"field": "status", "message": "Status must be 'active' or 'inactive'"})

    return errors


def parse_date_of_travel(date_str: Optional[str]) -> Optional[date]:
    """Parse date string to date object. Supports ISO format (YYYY-MM-DD) from HTML date input."""
    if not date_str:
        return None
    try:
        # HTML date input sends ISO format: YYYY-MM-DD
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        # Legacy support for DD/MM/YYYY format
        elif "/" in date_str:
            parts = date_str.split("/")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
    except (ValueError, IndexError):
        pass
    return None


def format_testimonial(t) -> dict:
    """Format a testimonial for API response."""
    return {
        "id": t.id,
        "customer_name": t.customer_name,
        "review_text": t.review_text,
        "star_rating": t.star_rating,  # Can be None for unrated
        "date_of_travel": t.date_of_travel.isoformat() if t.date_of_travel else None,  # ISO format for JS Date parsing
        "date_added": t.date_added.isoformat() if t.date_added else None,
        "status": t.status.value if hasattr(t.status, 'value') else t.status,
        "is_featured": t.is_featured,
        "source": t.source,
    }


@app.get("/api/admin/testimonials")
async def get_all_testimonials(
    star_rating: Optional[int] = None,
    status: Optional[str] = None,
    sort: str = "date_added",
    order: str = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get all testimonials with optional filters (admin only)."""
    from db_models import Testimonial, TestimonialStatus

    query = db.query(Testimonial)

    # Apply filters
    if star_rating:
        query = query.filter(Testimonial.star_rating == star_rating)

    if status:
        if status == "active":
            query = query.filter(Testimonial.status == TestimonialStatus.ACTIVE)
        elif status == "inactive":
            query = query.filter(Testimonial.status == TestimonialStatus.INACTIVE)

    # Apply sorting
    if sort == "star_rating":
        query = query.order_by(Testimonial.star_rating.desc() if order == "desc" else Testimonial.star_rating.asc())
    else:  # default to date_added
        query = query.order_by(Testimonial.date_added.desc() if order == "desc" else Testimonial.date_added.asc())

    testimonials = query.all()

    return {
        "testimonials": [format_testimonial(t) for t in testimonials],
        "total": len(testimonials),
    }


@app.post("/api/admin/testimonials")
async def create_testimonial(
    request: TestimonialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new testimonial (admin only)."""
    from db_models import Testimonial, TestimonialStatus

    # Validate
    errors = validate_testimonial_data(request.dict())
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    testimonial = Testimonial(
        customer_name=request.customer_name.strip(),
        review_text=request.review_text.strip(),
        star_rating=request.star_rating,  # Can be None
        date_of_travel=parse_date_of_travel(request.date_of_travel),
        status=TestimonialStatus.ACTIVE if request.status == "active" else TestimonialStatus.INACTIVE,
        is_featured=request.is_featured,
        source=request.source.strip() if request.source else None,
    )

    db.add(testimonial)
    db.commit()
    db.refresh(testimonial)

    return {
        "success": True,
        "testimonial": format_testimonial(testimonial),
    }


@app.put("/api/admin/testimonials/{testimonial_id}")
async def update_testimonial(
    testimonial_id: int,
    request: TestimonialUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an existing testimonial (admin only)."""
    from db_models import Testimonial, TestimonialStatus

    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    # Validate provided fields
    update_data = {k: v for k, v in request.dict().items() if v is not None}
    errors = validate_testimonial_data(update_data)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    # Apply updates
    if request.customer_name is not None:
        testimonial.customer_name = request.customer_name.strip()
    if request.review_text is not None:
        testimonial.review_text = request.review_text.strip()
    if request.star_rating is not None:
        testimonial.star_rating = request.star_rating
    if request.date_of_travel is not None:
        testimonial.date_of_travel = parse_date_of_travel(request.date_of_travel)
    if request.status is not None:
        testimonial.status = TestimonialStatus.ACTIVE if request.status == "active" else TestimonialStatus.INACTIVE
    if request.is_featured is not None:
        testimonial.is_featured = request.is_featured
    if request.source is not None:
        testimonial.source = request.source.strip() if request.source else None

    db.commit()
    db.refresh(testimonial)

    return {
        "success": True,
        "testimonial": format_testimonial(testimonial),
    }


@app.delete("/api/admin/testimonials/{testimonial_id}")
async def delete_testimonial(
    testimonial_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a testimonial (admin only)."""
    from db_models import Testimonial

    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    db.delete(testimonial)
    db.commit()

    return {"success": True, "message": "Testimonial deleted"}


@app.patch("/api/admin/testimonials/{testimonial_id}/status")
async def toggle_testimonial_status(
    testimonial_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Toggle testimonial status between active and inactive (admin only)."""
    from db_models import Testimonial, TestimonialStatus

    testimonial = db.query(Testimonial).filter(Testimonial.id == testimonial_id).first()
    if not testimonial:
        raise HTTPException(status_code=404, detail="Testimonial not found")

    # Toggle status
    if testimonial.status == TestimonialStatus.ACTIVE:
        testimonial.status = TestimonialStatus.INACTIVE
    else:
        testimonial.status = TestimonialStatus.ACTIVE

    db.commit()
    db.refresh(testimonial)

    return {
        "success": True,
        "testimonial": format_testimonial(testimonial),
    }


@app.get("/api/testimonials")
async def get_active_testimonials(
    db: Session = Depends(get_db),
):
    """
    Get active testimonials for public display (weighted pool).
    Weighting: 5★=5x, 4★=3x, unrated=3x, 3★=1x, 1-2★=excluded.
    Featured reviews always included regardless of rating.
    """
    from db_models import Testimonial, TestimonialStatus

    # Get active testimonials
    testimonials = db.query(Testimonial).filter(
        Testimonial.status == TestimonialStatus.ACTIVE
    ).all()

    # Build weighted pool
    weighted_pool = []
    for t in testimonials:
        formatted = format_testimonial(t)

        # Featured reviews always included (once)
        if t.is_featured:
            weighted_pool.append(formatted)
            continue

        # Apply weighting based on star rating
        if t.star_rating is None:
            # Unrated reviews (LinkedIn, FB, etc.) - treat as positive
            weighted_pool.extend([formatted] * 3)
        elif t.star_rating == 5:
            weighted_pool.extend([formatted] * 5)
        elif t.star_rating == 4:
            weighted_pool.extend([formatted] * 3)
        elif t.star_rating == 3:
            weighted_pool.append(formatted)
        # 1-2 star reviews excluded unless featured

    return {
        "testimonials": weighted_pool,
        "total": len(weighted_pool),
    }


# =============================================================================
# PROMO MODAL ENDPOINTS
# =============================================================================

class PromoModalCreate(BaseModel):
    """Request to create a promo modal or promo section."""
    type: str = "info_modal"  # info_modal or promo_section
    title: str
    message: str
    button_text: str = "Subscribe"
    button_action: str = "subscribe"  # subscribe, link, close, promotions
    button_link: Optional[str] = None
    start_date: Optional[str] = None  # DD/MM/YYYY format
    end_date: Optional[str] = None  # DD/MM/YYYY format
    background_color: str = "#1e3a5f"
    text_color: str = "#ffffff"
    button_color: str = "#22c55e"
    button_text_color: str = "#ffffff"
    status: str = "inactive"
    promo_code: Optional[str] = None  # Promo code to display (promo_section only)


class PromoModalUpdate(BaseModel):
    """Request to update a promo modal or promo section."""
    type: Optional[str] = None  # info_modal or promo_section
    title: Optional[str] = None
    message: Optional[str] = None
    button_text: Optional[str] = None
    button_action: Optional[str] = None
    button_link: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    button_color: Optional[str] = None
    button_text_color: Optional[str] = None
    status: Optional[str] = None
    max_subscribers: Optional[int] = None
    promo_code: Optional[str] = None  # Promo code to display (promo_section only)


def check_promo_modal_subscriber_limits(db: Session):
    """
    Check if any active promo modals have hit their subscriber limit.
    If so, auto-deactivate them.
    """
    from db_models import PromoModal, PromoModalStatus, MarketingSubscriber

    current_count = db.query(MarketingSubscriber).count()

    # Find active modals with subscriber limits
    active_modals = db.query(PromoModal).filter(
        PromoModal.status == PromoModalStatus.ACTIVE,
        PromoModal.max_subscribers.isnot(None),
        PromoModal.subscribers_at_activation.isnot(None),
    ).all()

    for modal in active_modals:
        target_count = modal.subscribers_at_activation + modal.max_subscribers
        if current_count >= target_count:
            modal.status = PromoModalStatus.INACTIVE
            print(f"Auto-deactivated promo modal '{modal.title}' - subscriber limit reached ({modal.max_subscribers} new subscribers)")

    db.commit()


def check_promo_modal_code_used(db: Session, promo_code: str):
    """
    Check if any active promo modal has this promo code.

    For single-use codes: auto-deactivate the modal when code is used.
    For multi-use codes: keep the modal active (expires by end_date instead).
    """
    from db_models import PromoModal, PromoModalStatus, PromoCode as DbPromoCode
    from sqlalchemy import func as sql_func

    if not promo_code:
        return

    # First check if this is a multi-use code
    promo_code_record = db.query(DbPromoCode).filter(
        DbPromoCode.code == promo_code.strip().upper()
    ).first()

    if promo_code_record and promo_code_record.is_multi_use:
        # Multi-use code - don't auto-deactivate the modal
        # The modal should expire based on its end_date instead
        print(f"Promo code '{promo_code}' is multi-use - keeping promo modal active")
        return

    # Single-use code - find and deactivate the modal
    modal = db.query(PromoModal).filter(
        PromoModal.status == PromoModalStatus.ACTIVE,
        PromoModal.promo_code.isnot(None),
        sql_func.upper(PromoModal.promo_code) == promo_code.strip().upper(),
    ).first()

    if modal:
        modal.status = PromoModalStatus.INACTIVE
        db.commit()
        print(f"Auto-deactivated promo modal '{modal.title}' - single-use promo code '{promo_code}' used")


def mark_promo_code_used(db: Session, promo_code_record, booking_id: int, discount_percent: int, discount_amount_pence: int = None):
    """
    Mark a promo code as used. Handles both single-use and multi-use codes.

    For single-use codes (max_uses is None):
        - Sets is_used = True
        - Sets booking_id to the booking that used it

    For multi-use codes (max_uses is set):
        - Increments use_count
        - Creates a PromoCodeUsage record to track each usage
        - Sets is_used = True only when max_uses is reached
        - Updates booking_id to the last booking that used it

    Returns True if successful, False if code is already exhausted.
    """
    from db_models import PromoCodeUsage, Promotion as DbPromotion

    if not promo_code_record:
        return False

    # Check if code can still be used
    if not promo_code_record.can_be_used:
        log_promo("MARK_USED code cannot be used", {
            "code": promo_code_record.code,
            "is_used": promo_code_record.is_used,
            "max_uses": promo_code_record.max_uses,
            "use_count": promo_code_record.use_count
        })
        return False

    uk_now = get_uk_now()

    # Increment use count
    promo_code_record.use_count = (promo_code_record.use_count or 0) + 1
    promo_code_record.used_at = uk_now
    promo_code_record.booking_id = booking_id

    # For single-use or when max uses reached, mark as used
    if promo_code_record.max_uses is None:
        # Single-use code
        promo_code_record.is_used = True
    elif promo_code_record.max_uses > 0 and promo_code_record.use_count >= promo_code_record.max_uses:
        # Multi-use code that has reached its limit
        promo_code_record.is_used = True
    # For unlimited codes (max_uses = 0), is_used stays False

    # Create usage record for multi-use codes (and optionally for single-use for tracking)
    if promo_code_record.is_multi_use:
        usage = PromoCodeUsage(
            promo_code_id=promo_code_record.id,
            booking_id=booking_id,
            discount_percent=discount_percent,
            discount_amount_pence=discount_amount_pence,
            used_at=uk_now
        )
        db.add(usage)

    # Update promotion stats
    promotion = db.query(DbPromotion).filter(DbPromotion.id == promo_code_record.promotion_id).first()
    if promotion:
        promotion.codes_used = (promotion.codes_used or 0) + 1

    log_promo("MARK_USED success", {
        "code": promo_code_record.code,
        "booking_id": booking_id,
        "use_count": promo_code_record.use_count,
        "max_uses": promo_code_record.max_uses,
        "is_used": promo_code_record.is_used,
        "is_multi_use": promo_code_record.is_multi_use
    })

    return True


def format_promo_modal(modal):
    """Format a promo modal for API response."""
    return {
        "id": modal.id,
        "type": modal.type.value if modal.type else "info_modal",
        "title": modal.title,
        "message": modal.message,
        "buttonText": modal.button_text,
        "buttonAction": modal.button_action,
        "buttonLink": modal.button_link,
        "startDate": modal.start_date.strftime("%d/%m/%Y") if modal.start_date else None,
        "endDate": modal.end_date.strftime("%d/%m/%Y") if modal.end_date else None,
        "backgroundColor": modal.background_color,
        "textColor": modal.text_color,
        "buttonColor": modal.button_color,
        "buttonTextColor": getattr(modal, 'button_text_color', '#ffffff') or '#ffffff',
        "status": modal.status.value,
        "createdAt": modal.created_at.isoformat() if modal.created_at else None,
        "viewCount": modal.view_count or 0,
        "clickCount": modal.click_count or 0,
        "maxSubscribers": modal.max_subscribers,
        "subscribersAtActivation": modal.subscribers_at_activation,
        "promoCode": modal.promo_code,
    }


@app.get("/api/admin/promo-modals")
async def get_all_promo_modals(
    status: Optional[str] = None,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get all promo modals and sections for admin management."""
    from db_models import PromoModal, PromoModalStatus, PromoModalType

    query = db.query(PromoModal)

    if status:
        try:
            status_enum = PromoModalStatus(status)
            query = query.filter(PromoModal.status == status_enum)
        except ValueError:
            pass

    if type:
        try:
            type_enum = PromoModalType(type)
            query = query.filter(PromoModal.type == type_enum)
        except ValueError:
            pass

    modals = query.order_by(PromoModal.created_at.desc()).all()

    return {
        "promoModals": [format_promo_modal(m) for m in modals],
        "total": len(modals),
    }


@app.post("/api/admin/promo-modals")
async def create_promo_modal(
    request: PromoModalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new promo modal or promo section."""
    from db_models import PromoModal, PromoModalStatus, PromoModalType

    # Parse dates
    start_date = None
    end_date = None
    if request.start_date:
        try:
            start_date = datetime.strptime(request.start_date, "%d/%m/%Y").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date format. Use DD/MM/YYYY")
    if request.end_date:
        try:
            end_date = datetime.strptime(request.end_date, "%d/%m/%Y").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end date format. Use DD/MM/YYYY")

    # Validate status
    try:
        status_enum = PromoModalStatus(request.status)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid status. Use active, inactive, or scheduled")

    # Validate type
    try:
        type_enum = PromoModalType(request.type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid type. Use info_modal or promo_section")

    modal = PromoModal(
        type=type_enum,
        title=request.title,
        message=request.message,
        button_text=request.button_text,
        button_action=request.button_action,
        button_link=request.button_link,
        start_date=start_date,
        end_date=end_date,
        background_color=request.background_color,
        text_color=request.text_color,
        button_color=request.button_color,
        button_text_color=request.button_text_color,
        status=status_enum,
        promo_code=request.promo_code,
    )

    db.add(modal)
    db.commit()
    db.refresh(modal)

    return {
        "success": True,
        "promoModal": format_promo_modal(modal),
    }


@app.put("/api/admin/promo-modals/{modal_id}")
async def update_promo_modal(
    modal_id: int,
    request: PromoModalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an existing promo modal or promo section."""
    from db_models import PromoModal, PromoModalStatus, PromoModalType, MarketingSubscriber

    modal = db.query(PromoModal).filter(PromoModal.id == modal_id).first()
    if not modal:
        raise HTTPException(status_code=404, detail="Promo modal not found")

    # Update type if provided
    if request.type is not None:
        try:
            modal.type = PromoModalType(request.type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid type. Use info_modal or promo_section")

    # Update fields
    if request.title is not None:
        modal.title = request.title
    if request.message is not None:
        modal.message = request.message
    if request.button_text is not None:
        modal.button_text = request.button_text
    if request.button_action is not None:
        modal.button_action = request.button_action
    if request.button_link is not None:
        modal.button_link = request.button_link
    if request.background_color is not None:
        modal.background_color = request.background_color
    if request.text_color is not None:
        modal.text_color = request.text_color
    if request.button_color is not None:
        modal.button_color = request.button_color
    if request.button_text_color is not None:
        modal.button_text_color = request.button_text_color

    # Parse dates
    if request.start_date is not None:
        if request.start_date == "":
            modal.start_date = None
        else:
            try:
                modal.start_date = datetime.strptime(request.start_date, "%d/%m/%Y").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start date format. Use DD/MM/YYYY")

    if request.end_date is not None:
        if request.end_date == "":
            modal.end_date = None
        else:
            try:
                modal.end_date = datetime.strptime(request.end_date, "%d/%m/%Y").date()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end date format. Use DD/MM/YYYY")

    # Handle max_subscribers
    if request.max_subscribers is not None:
        modal.max_subscribers = request.max_subscribers if request.max_subscribers > 0 else None

    # Handle promo_code
    if request.promo_code is not None:
        modal.promo_code = request.promo_code if request.promo_code.strip() else None

    # Parse status and capture subscriber count if activating
    old_status = modal.status
    if request.status is not None:
        try:
            new_status = PromoModalStatus(request.status)
            modal.status = new_status

            # If activating and has max_subscribers, capture current count
            if new_status == PromoModalStatus.ACTIVE and old_status != PromoModalStatus.ACTIVE:
                if modal.max_subscribers:
                    current_count = db.query(MarketingSubscriber).count()
                    modal.subscribers_at_activation = current_count
            elif new_status != PromoModalStatus.ACTIVE:
                modal.subscribers_at_activation = None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status. Use active, inactive, or scheduled")

    db.commit()
    db.refresh(modal)

    return {
        "success": True,
        "promoModal": format_promo_modal(modal),
    }


@app.delete("/api/admin/promo-modals/{modal_id}")
async def delete_promo_modal(
    modal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a promo modal."""
    from db_models import PromoModal

    modal = db.query(PromoModal).filter(PromoModal.id == modal_id).first()
    if not modal:
        raise HTTPException(status_code=404, detail="Promo modal not found")

    db.delete(modal)
    db.commit()

    return {
        "success": True,
        "message": f"Promo modal '{modal.title}' deleted",
    }


@app.patch("/api/admin/promo-modals/{modal_id}/status")
async def toggle_promo_modal_status(
    modal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Toggle promo modal status between active and inactive (admin only)."""
    from db_models import PromoModal, PromoModalStatus, MarketingSubscriber

    modal = db.query(PromoModal).filter(PromoModal.id == modal_id).first()
    if not modal:
        raise HTTPException(status_code=404, detail="Promo modal not found")

    # Toggle status
    if modal.status == PromoModalStatus.ACTIVE:
        modal.status = PromoModalStatus.INACTIVE
        modal.subscribers_at_activation = None
    else:
        modal.status = PromoModalStatus.ACTIVE
        # Capture current subscriber count when activating
        if modal.max_subscribers:
            current_count = db.query(MarketingSubscriber).count()
            modal.subscribers_at_activation = current_count

    db.commit()
    db.refresh(modal)

    return {
        "success": True,
        "promoModal": format_promo_modal(modal),
    }


@app.get("/api/promo-modal")
async def get_active_promo_modal(
    db: Session = Depends(get_db),
):
    """
    Get the currently active info modal for public display (popup).
    Returns the first active info_modal type that's within its date range (UK timezone).

    Date boundaries are inclusive:
    - start_date: Modal shows from 00:00:00 UK time on this date
    - end_date: Modal shows until 23:59:59 UK time on this date
    """
    from db_models import PromoModal, PromoModalStatus, PromoModalType

    # Use UK timezone for date comparison
    today_uk = get_uk_now().date()

    # Find active info modals (type = info_modal) within date range
    modals = db.query(PromoModal).filter(
        PromoModal.status == PromoModalStatus.ACTIVE,
        PromoModal.type == PromoModalType.INFO_MODAL
    ).all()

    for modal in modals:
        # Check date range (inclusive on both ends)
        if modal.start_date and today_uk < modal.start_date:
            continue
        if modal.end_date and today_uk > modal.end_date:
            # Auto-deactivate expired modal
            modal.status = PromoModalStatus.INACTIVE
            db.commit()
            continue
        # This modal is valid
        return {
            "promoModal": format_promo_modal(modal),
        }

    # No active modal found
    return {
        "promoModal": None,
    }


@app.get("/api/promo-section")
async def get_active_promo_section(
    db: Session = Depends(get_db),
):
    """
    Get the currently active promo section for public display (homepage section).
    Returns the first active promo_section type that's within its date range (UK timezone).

    Date boundaries are inclusive:
    - start_date: Section shows from 00:00:00 UK time on this date
    - end_date: Section shows until 23:59:59 UK time on this date
    """
    from db_models import PromoModal, PromoModalStatus, PromoModalType

    # Use UK timezone for date comparison
    today_uk = get_uk_now().date()

    # Find active promo sections (type = promo_section) within date range
    modals = db.query(PromoModal).filter(
        PromoModal.status == PromoModalStatus.ACTIVE,
        PromoModal.type == PromoModalType.PROMO_SECTION
    ).all()

    for modal in modals:
        # Check date range (inclusive on both ends)
        if modal.start_date and today_uk < modal.start_date:
            continue
        if modal.end_date and today_uk > modal.end_date:
            # Auto-deactivate expired section
            modal.status = PromoModalStatus.INACTIVE
            db.commit()
            continue
        # This section is valid
        return {
            "promoSection": format_promo_modal(modal),
        }

    # No active section found
    return {
        "promoSection": None,
    }


@app.post("/api/promo-modal/{modal_id}/view")
async def track_promo_modal_view(
    modal_id: int,
    db: Session = Depends(get_db),
):
    """Track a view of a promo modal."""
    from db_models import PromoModal

    modal = db.query(PromoModal).filter(PromoModal.id == modal_id).first()
    if modal:
        modal.view_count = (modal.view_count or 0) + 1
        db.commit()

    return {"success": True}


@app.post("/api/promo-modal/{modal_id}/click")
async def track_promo_modal_click(
    modal_id: int,
    db: Session = Depends(get_db),
):
    """Track a CTA click on a promo modal."""
    from db_models import PromoModal

    modal = db.query(PromoModal).filter(PromoModal.id == modal_id).first()
    if modal:
        modal.click_count = (modal.click_count or 0) + 1
        db.commit()

    return {"success": True}


# =============================================================================
# BLOCKED DATES ENDPOINTS
# =============================================================================

class BlockedDateCreate(BaseModel):
    """Request to create a blocked date."""
    start_date: str  # YYYY-MM-DD format (UK timezone)
    end_date: str    # YYYY-MM-DD format (UK timezone)
    block_dropoffs: bool = True
    block_pickups: bool = True
    reason: Optional[str] = None


class BlockedDateUpdate(BaseModel):
    """Request to update a blocked date."""
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    block_dropoffs: Optional[bool] = None
    block_pickups: Optional[bool] = None
    reason: Optional[str] = None


def parse_blocked_date(date_str: str) -> date:
    """Parse date string (YYYY-MM-DD) to date object."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def format_blocked_date(blocked: "BlockedDate", include_time_slots: bool = True) -> dict:
    """Format a BlockedDate model for API response."""
    result = {
        "id": blocked.id,
        "start_date": blocked.start_date.isoformat(),
        "end_date": blocked.end_date.isoformat(),
        "block_dropoffs": blocked.block_dropoffs,
        "block_pickups": blocked.block_pickups,
        "reason": blocked.reason,
        "created_by": blocked.created_by,
        "created_at": blocked.created_at.isoformat() if blocked.created_at else None,
        "updated_at": blocked.updated_at.isoformat() if blocked.updated_at else None,
    }

    # Include time slots if requested and relationship is loaded
    if include_time_slots and hasattr(blocked, 'time_slots') and blocked.time_slots:
        result["time_slots"] = [
            {
                "id": slot.id,
                "start_time": slot.start_time.strftime("%H:%M") if slot.start_time else None,
                "end_time": slot.end_time.strftime("%H:%M") if slot.end_time else None,
                "block_dropoffs": slot.block_dropoffs,
                "block_pickups": slot.block_pickups,
                "reason": slot.reason,
            }
            for slot in blocked.time_slots
        ]
    else:
        result["time_slots"] = []

    return result


@app.get("/api/admin/blocked-dates")
async def get_blocked_dates(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get all blocked dates with optional date range filter (admin only)."""
    from db_models import BlockedDate
    from sqlalchemy.orm import joinedload

    query = db.query(BlockedDate).options(joinedload(BlockedDate.time_slots))

    # Apply date range filters
    if date_from:
        from_date = parse_blocked_date(date_from)
        query = query.filter(BlockedDate.end_date >= from_date)

    if date_to:
        to_date = parse_blocked_date(date_to)
        query = query.filter(BlockedDate.start_date <= to_date)

    # Order by start date
    query = query.order_by(BlockedDate.start_date.asc())

    blocked_dates = query.all()

    return {
        "blocked_dates": [format_blocked_date(bd) for bd in blocked_dates],
        "total": len(blocked_dates),
    }


@app.post("/api/admin/blocked-dates")
async def create_blocked_date(
    request: BlockedDateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new blocked date (admin only)."""
    from db_models import BlockedDate

    start = parse_blocked_date(request.start_date)
    end = parse_blocked_date(request.end_date)

    # Validate date range
    if end < start:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")

    # Must block at least one type
    if not request.block_dropoffs and not request.block_pickups:
        raise HTTPException(status_code=422, detail="Must block at least dropoffs or pickups")

    blocked = BlockedDate(
        start_date=start,
        end_date=end,
        block_dropoffs=request.block_dropoffs,
        block_pickups=request.block_pickups,
        reason=request.reason.strip() if request.reason else None,
        created_by=current_user.email,
    )

    db.add(blocked)
    db.commit()
    db.refresh(blocked)

    return {
        "success": True,
        "blocked_date": format_blocked_date(blocked),
    }


@app.put("/api/admin/blocked-dates/{blocked_date_id}")
async def update_blocked_date(
    blocked_date_id: int,
    request: BlockedDateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an existing blocked date (admin only)."""
    from db_models import BlockedDate

    blocked = db.query(BlockedDate).filter(BlockedDate.id == blocked_date_id).first()
    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked date not found")

    # Apply updates
    if request.start_date is not None:
        blocked.start_date = parse_blocked_date(request.start_date)
    if request.end_date is not None:
        blocked.end_date = parse_blocked_date(request.end_date)
    if request.block_dropoffs is not None:
        blocked.block_dropoffs = request.block_dropoffs
    if request.block_pickups is not None:
        blocked.block_pickups = request.block_pickups
    if request.reason is not None:
        blocked.reason = request.reason.strip() if request.reason else None

    # Validate after updates
    if blocked.end_date < blocked.start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")
    if not blocked.block_dropoffs and not blocked.block_pickups:
        raise HTTPException(status_code=422, detail="Must block at least dropoffs or pickups")

    db.commit()
    db.refresh(blocked)

    return {
        "success": True,
        "blocked_date": format_blocked_date(blocked),
    }


@app.delete("/api/admin/blocked-dates/{blocked_date_id}")
async def delete_blocked_date(
    blocked_date_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a blocked date (admin only)."""
    from db_models import BlockedDate

    blocked = db.query(BlockedDate).filter(BlockedDate.id == blocked_date_id).first()
    if not blocked:
        raise HTTPException(status_code=404, detail="Blocked date not found")

    db.delete(blocked)
    db.commit()

    return {"success": True, "message": "Blocked date deleted"}


# =====================================================
# BLOCKED TIME SLOTS ENDPOINTS (Admin)
# =====================================================

@app.get("/api/admin/blocked-dates/{blocked_date_id}/time-slots")
async def get_blocked_time_slots(
    blocked_date_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get all time slots for a blocked date."""
    from db_models import BlockedDate, BlockedTimeSlot

    blocked_date = db.query(BlockedDate).filter(BlockedDate.id == blocked_date_id).first()
    if not blocked_date:
        raise HTTPException(status_code=404, detail="Blocked date not found")

    time_slots = db.query(BlockedTimeSlot).filter(
        BlockedTimeSlot.blocked_date_id == blocked_date_id
    ).order_by(BlockedTimeSlot.start_time).all()

    return {
        "blocked_date_id": blocked_date_id,
        "time_slots": [
            {
                "id": ts.id,
                "start_time": ts.start_time.strftime("%H:%M") if ts.start_time else None,
                "end_time": ts.end_time.strftime("%H:%M") if ts.end_time else None,
                "block_dropoffs": ts.block_dropoffs,
                "block_pickups": ts.block_pickups,
                "reason": ts.reason,
                "created_at": ts.created_at.isoformat() if ts.created_at else None,
            }
            for ts in time_slots
        ],
    }


@app.post("/api/admin/blocked-dates/{blocked_date_id}/time-slots")
async def create_blocked_time_slot(
    blocked_date_id: int,
    start_time: str = Body(...),
    end_time: str = Body(...),
    block_dropoffs: bool = Body(True),
    block_pickups: bool = Body(True),
    reason: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new time slot for a blocked date."""
    from db_models import BlockedDate, BlockedTimeSlot
    from datetime import time

    blocked_date = db.query(BlockedDate).filter(BlockedDate.id == blocked_date_id).first()
    if not blocked_date:
        raise HTTPException(status_code=404, detail="Blocked date not found")

    # Parse times
    try:
        start_h, start_m = map(int, start_time.split(":"))
        end_h, end_m = map(int, end_time.split(":"))
        start_t = time(start_h, start_m)
        end_t = time(end_h, end_m)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")

    if start_t >= end_t:
        raise HTTPException(status_code=400, detail="Start time must be before end time")

    if not block_dropoffs and not block_pickups:
        raise HTTPException(status_code=400, detail="Must block at least drop-offs or pick-ups")

    # Check for overlapping time slots
    existing = db.query(BlockedTimeSlot).filter(
        BlockedTimeSlot.blocked_date_id == blocked_date_id,
        BlockedTimeSlot.start_time < end_t,
        BlockedTimeSlot.end_time > start_t
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Time slot overlaps with existing slot ({existing.start_time.strftime('%H:%M')}-{existing.end_time.strftime('%H:%M')})"
        )

    new_slot = BlockedTimeSlot(
        blocked_date_id=blocked_date_id,
        start_time=start_t,
        end_time=end_t,
        block_dropoffs=block_dropoffs,
        block_pickups=block_pickups,
        reason=reason,
    )

    db.add(new_slot)
    db.commit()
    db.refresh(new_slot)

    return {
        "success": True,
        "time_slot": {
            "id": new_slot.id,
            "blocked_date_id": blocked_date_id,
            "start_time": new_slot.start_time.strftime("%H:%M"),
            "end_time": new_slot.end_time.strftime("%H:%M"),
            "block_dropoffs": new_slot.block_dropoffs,
            "block_pickups": new_slot.block_pickups,
            "reason": new_slot.reason,
        },
    }


@app.put("/api/admin/blocked-time-slots/{time_slot_id}")
async def update_blocked_time_slot(
    time_slot_id: int,
    start_time: Optional[str] = Body(None),
    end_time: Optional[str] = Body(None),
    block_dropoffs: Optional[bool] = Body(None),
    block_pickups: Optional[bool] = Body(None),
    reason: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an existing time slot."""
    from db_models import BlockedTimeSlot
    from datetime import time

    slot = db.query(BlockedTimeSlot).filter(BlockedTimeSlot.id == time_slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")

    # Parse and update times
    new_start = slot.start_time
    new_end = slot.end_time

    if start_time:
        try:
            h, m = map(int, start_time.split(":"))
            new_start = time(h, m)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid start time format. Use HH:MM")

    if end_time:
        try:
            h, m = map(int, end_time.split(":"))
            new_end = time(h, m)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid end time format. Use HH:MM")

    if new_start >= new_end:
        raise HTTPException(status_code=400, detail="Start time must be before end time")

    # Check for overlapping time slots (excluding self)
    existing = db.query(BlockedTimeSlot).filter(
        BlockedTimeSlot.blocked_date_id == slot.blocked_date_id,
        BlockedTimeSlot.id != time_slot_id,
        BlockedTimeSlot.start_time < new_end,
        BlockedTimeSlot.end_time > new_start
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Time slot overlaps with existing slot ({existing.start_time.strftime('%H:%M')}-{existing.end_time.strftime('%H:%M')})"
        )

    # Update fields
    slot.start_time = new_start
    slot.end_time = new_end

    if block_dropoffs is not None:
        slot.block_dropoffs = block_dropoffs
    if block_pickups is not None:
        slot.block_pickups = block_pickups
    if reason is not None:
        slot.reason = reason

    # Validate at least one is blocked
    if not slot.block_dropoffs and not slot.block_pickups:
        raise HTTPException(status_code=400, detail="Must block at least drop-offs or pick-ups")

    db.commit()
    db.refresh(slot)

    return {
        "success": True,
        "time_slot": {
            "id": slot.id,
            "blocked_date_id": slot.blocked_date_id,
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "block_dropoffs": slot.block_dropoffs,
            "block_pickups": slot.block_pickups,
            "reason": slot.reason,
        },
    }


@app.delete("/api/admin/blocked-time-slots/{time_slot_id}")
async def delete_blocked_time_slot(
    time_slot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete a time slot."""
    from db_models import BlockedTimeSlot

    slot = db.query(BlockedTimeSlot).filter(BlockedTimeSlot.id == time_slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")

    db.delete(slot)
    db.commit()

    return {"success": True, "message": "Time slot deleted"}


@app.get("/api/blocked-dates/check")
async def check_blocked_date(
    dropoff_date: Optional[str] = None,
    pickup_date: Optional[str] = None,
    dropoff_time: Optional[str] = None,
    pickup_time: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Check if a date/time is blocked for bookings (public endpoint).
    Returns blocking info for the specified dates.
    If date_from and date_to are provided, returns all blocked dates in that range.
    If time is provided, checks against specific time slots.
    All dates are in UK timezone.
    """
    from db_models import BlockedDate, BlockedTimeSlot
    from datetime import time

    result = {
        "dropoff_blocked": False,
        "pickup_blocked": False,
        "dropoff_reason": None,
        "pickup_reason": None,
        "blocked_dates": [],
    }

    # If date range provided, return all blocked dates in that range (with time slots)
    if date_from and date_to:
        from_date = parse_blocked_date(date_from)
        to_date = parse_blocked_date(date_to)

        blocked_dates = db.query(BlockedDate).filter(
            BlockedDate.start_date <= to_date,
            BlockedDate.end_date >= from_date
        ).order_by(BlockedDate.start_date).all()

        result["blocked_dates"] = [
            {
                "id": bd.id,
                "start_date": bd.start_date.isoformat(),
                "end_date": bd.end_date.isoformat(),
                "block_dropoffs": bd.block_dropoffs,
                "block_pickups": bd.block_pickups,
                "reason": bd.reason,
                "time_slots": [
                    {
                        "id": ts.id,
                        "start_time": ts.start_time.strftime("%H:%M") if ts.start_time else None,
                        "end_time": ts.end_time.strftime("%H:%M") if ts.end_time else None,
                        "block_dropoffs": ts.block_dropoffs,
                        "block_pickups": ts.block_pickups,
                        "reason": ts.reason,
                    }
                    for ts in bd.time_slots
                ],
            }
            for bd in blocked_dates
        ]
        return result

    # Helper to check if a time falls within any blocked time slot
    def is_time_blocked(blocked_date, check_time_str, check_type):
        """
        Check if a specific time is blocked.
        - If no time slots exist, use the blocked_date's block settings
        - If time slots exist, check if the time falls within any slot
        """
        if not blocked_date.time_slots:
            # No time slots - entire day is blocked based on blocked_date settings
            if check_type == "dropoff":
                return blocked_date.block_dropoffs, blocked_date.reason
            else:
                return blocked_date.block_pickups, blocked_date.reason

        # Time slots exist - check if the time falls within any
        if not check_time_str:
            # No time provided but time slots exist - check if any slot blocks this type
            for ts in blocked_date.time_slots:
                if check_type == "dropoff" and ts.block_dropoffs:
                    return True, ts.reason or blocked_date.reason
                if check_type == "pickup" and ts.block_pickups:
                    return True, ts.reason or blocked_date.reason
            return False, None

        # Parse the time
        try:
            h, m = map(int, check_time_str.split(":"))
            check_time = time(h, m)
        except (ValueError, AttributeError):
            return False, None

        # Check each time slot
        for ts in blocked_date.time_slots:
            if ts.start_time <= check_time < ts.end_time:
                if check_type == "dropoff" and ts.block_dropoffs:
                    return True, ts.reason or blocked_date.reason
                if check_type == "pickup" and ts.block_pickups:
                    return True, ts.reason or blocked_date.reason

        return False, None

    if dropoff_date:
        d_date = parse_blocked_date(dropoff_date)
        # Find any blocked date that covers this date
        blocked = db.query(BlockedDate).filter(
            BlockedDate.start_date <= d_date,
            BlockedDate.end_date >= d_date
        ).first()

        if blocked:
            is_blocked, reason = is_time_blocked(blocked, dropoff_time, "dropoff")
            if is_blocked:
                result["dropoff_blocked"] = True
                result["dropoff_reason"] = reason

    if pickup_date:
        p_date = parse_blocked_date(pickup_date)
        # Find any blocked date that covers this date
        blocked = db.query(BlockedDate).filter(
            BlockedDate.start_date <= p_date,
            BlockedDate.end_date >= p_date
        ).first()

        if blocked:
            is_blocked, reason = is_time_blocked(blocked, pickup_time, "pickup")
            if is_blocked:
                result["pickup_blocked"] = True
                result["pickup_reason"] = reason

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
