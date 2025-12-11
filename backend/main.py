"""
FastAPI application for TAG booking system.

Provides REST API endpoints for the frontend to:
- Get available time slots for flights
- Create bookings (which hides the booked slot)
- Check parking capacity
- Manage bookings
- Process Stripe payments
"""
import uuid
from datetime import date, time, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
from db_models import BookingStatus, PaymentStatus, FlightDeparture, FlightArrival
import db_service


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


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    init_db()


# Path to flight schedule
FLIGHTS_DATA_PATH = Path(__file__).parent.parent / "tag-website" / "src" / "data" / "flightSchedule.json"


def get_service() -> BookingService:
    """Get the booking service instance."""
    path = str(FLIGHTS_DATA_PATH) if FLIGHTS_DATA_PATH.exists() else None
    return get_booking_service(path)


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
):
    """
    Admin endpoint: Get all active bookings.

    Optionally filter by a specific date to see which vehicles
    will be parked on that day.
    """
    service = get_service()

    if date_filter:
        bookings = service.get_bookings_for_date(date_filter)
    else:
        bookings = service.get_all_active_bookings()

    return {
        "count": len(bookings),
        "date_filter": date_filter.isoformat() if date_filter else None,
        "bookings": bookings,
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


# =============================================================================
# Flight Schedule Endpoints (from database)
# =============================================================================

@app.get("/api/flights/departures/{flight_date}")
async def get_departures_for_date(flight_date: date, db: Session = Depends(get_db)):
    """
    Get all departure flights for a specific date.

    Returns flights in a format compatible with the frontend:
    - date, type, time, airlineCode, airlineName, destinationCode, destinationName, flightNumber
    - Also includes slot availability (is_slot_1_booked, is_slot_2_booked)
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
            "is_slot_1_booked": d.is_slot_1_booked,
            "is_slot_2_booked": d.is_slot_2_booked,
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
            "is_slot_1_booked": d.is_slot_1_booked,
            "is_slot_2_booked": d.is_slot_2_booked,
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
    slot_id: str = Query(..., description="Slot ID: '165' for slot 1, '120' for slot 2"),
    db: Session = Depends(get_db)
):
    """
    Book a slot on a departure flight.

    Slot 1 (id='165'): 2¾ hours before departure
    Slot 2 (id='120'): 2 hours before departure
    """
    # Convert slot_id to slot_number
    slot_number = 1 if slot_id == "165" else 2 if slot_id == "120" else None
    if slot_number is None:
        raise HTTPException(status_code=400, detail="Invalid slot ID. Use '165' or '120'")

    success = db_service.book_departure_slot(db, departure_id, slot_number)
    if not success:
        raise HTTPException(status_code=400, detail="Slot already booked or flight not found")

    return {"success": True, "message": f"Slot {slot_number} booked successfully"}


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


class UpdateCustomerBillingRequest(BaseModel):
    """Request to update customer billing address from Step 5."""
    billing_address1: str
    billing_address2: Optional[str] = None
    billing_city: str
    billing_county: Optional[str] = None
    billing_postcode: str
    billing_country: str = "United Kingdom"


class CreateVehicleRequest(BaseModel):
    """Request to create/update vehicle from Step 3."""
    customer_id: int
    registration: str
    make: str
    model: str
    colour: str


@app.post("/api/customers")
async def create_or_update_customer(request: CreateCustomerRequest, db: Session = Depends(get_db)):
    """
    Create or update a customer (Step 1: Contact Details).

    If a customer with this email exists, updates their details.
    Returns the customer ID for use in subsequent steps.
    """
    try:
        customer = db_service.create_customer(
            db=db,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            phone=request.phone,
        )
        return {
            "success": True,
            "customer_id": customer.id,
            "message": "Customer saved successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/customers/{customer_id}/billing")
async def update_customer_billing(
    customer_id: int,
    request: UpdateCustomerBillingRequest,
    db: Session = Depends(get_db)
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

        return {
            "success": True,
            "customer_id": customer.id,
            "message": "Billing address saved successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/vehicles")
async def create_or_update_vehicle(request: CreateVehicleRequest, db: Session = Depends(get_db)):
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
        vehicle = db_service.create_vehicle(
            db=db,
            customer_id=request.customer_id,
            registration=request.registration,
            make=request.make,
            model=request.model,
            colour=request.colour,
        )
        return {
            "success": True,
            "vehicle_id": vehicle.id,
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
async def lookup_vehicle(request: VehicleLookupRequest):
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
                print(f"DVLA API 403: {response.text}")
                return VehicleLookupResponse(
                    success=False,
                    registration=clean_reg,
                    error="DVLA API access denied - check API key"
                )
            else:
                # Log error for debugging
                print(f"DVLA API error: {response.status_code} - {response.text}")
                return VehicleLookupResponse(
                    success=False,
                    registration=clean_reg,
                    error=f"DVLA error ({response.status_code})"
                )

    except httpx.TimeoutException:
        return VehicleLookupResponse(
            success=False,
            registration=clean_reg,
            error="DVLA service timeout"
        )
    except Exception as e:
        print(f"DVLA lookup error: {e}")
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
async def lookup_address(request: AddressLookupRequest):
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
                print(f"OS Places API 401: {response.text}")
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error="Address service authentication failed"
                )
            else:
                print(f"OS Places API error: {response.status_code} - {response.text}")
                return AddressLookupResponse(
                    success=False,
                    postcode=clean_postcode,
                    error=f"Address lookup failed ({response.status_code})"
                )

    except httpx.TimeoutException:
        return AddressLookupResponse(
            success=False,
            postcode=clean_postcode,
            error="Address service timeout"
        )
    except Exception as e:
        print(f"Address lookup error: {e}")
        return AddressLookupResponse(
            success=False,
            postcode=clean_postcode,
            error="Unable to lookup address"
        )


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
    pickup_flight_time: Optional[str] = None  # Landing time "HH:MM"
    pickup_flight_number: Optional[str] = None
    pickup_origin: Optional[str] = None


class CreatePaymentResponse(BaseModel):
    """Response with payment intent details for frontend."""
    client_secret: str
    payment_intent_id: str
    booking_reference: str
    amount: int
    amount_display: str  # e.g., "£99.00"
    publishable_key: str


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
async def create_payment(request: CreatePaymentRequest, db: Session = Depends(get_db)):
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

    # Calculate amount in pence
    amount = calculate_price_in_pence(request.package)

    try:
        # Parse dates
        dropoff_date = datetime.strptime(request.drop_off_date, "%Y-%m-%d").date()
        pickup_date = datetime.strptime(request.pickup_date, "%Y-%m-%d").date()

        # Parse drop-off time if provided
        dropoff_time = time(12, 0)  # Default to noon
        if request.drop_off_time:
            time_parts = request.drop_off_time.split(":")
            dropoff_time = time(int(time_parts[0]), int(time_parts[1]))

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
                pickup_time=pickup_time,
                pickup_time_from=pickup_time_from,
                pickup_time_to=pickup_time_to,
                pickup_flight_number=request.pickup_flight_number,
                pickup_origin=request.pickup_origin,
            )
            booking_reference = booking.reference
            booking_id = booking.id
        else:
            # Fallback: Create everything from scratch (backwards compatible)
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
                pickup_time=pickup_time,
                pickup_time_from=pickup_time_from,
                pickup_time_to=pickup_time_to,
                pickup_flight_number=request.pickup_flight_number,
                pickup_origin=request.pickup_origin,
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
                # Check if both slots are booked (fully booked)
                if departure.is_slot_1_booked and departure.is_slot_2_booked:
                    raise HTTPException(
                        status_code=400,
                        detail="This flight is fully booked. Please contact us directly at hello@tagparking.com to arrange an alternative."
                    )

                # Slot "165" = 2¾ hours before = slot 1
                # Slot "120" = 2 hours before = slot 2
                if request.drop_off_slot == "165" and departure.is_slot_1_booked:
                    raise HTTPException(
                        status_code=400,
                        detail="This slot is already booked. Please select the other available slot or contact us directly."
                    )
                elif request.drop_off_slot == "120" and departure.is_slot_2_booked:
                    raise HTTPException(
                        status_code=400,
                        detail="This slot is already booked. Please select the other available slot or contact us directly."
                    )
                # Note: Slot is NOT booked here - it will be booked after payment succeeds via webhook

        # Create Stripe PaymentIntent
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
        )

        intent = create_payment_intent(intent_request)

        # Create payment record linked to booking
        db_service.create_payment(
            db=db,
            booking_id=booking_id,
            stripe_payment_intent_id=intent.payment_intent_id,
            amount_pence=amount,
        )

        settings = get_settings()

        return CreatePaymentResponse(
            client_secret=intent.client_secret,
            payment_intent_id=intent.payment_intent_id,
            booking_reference=booking_reference,
            amount=amount,
            amount_display=f"£{amount / 100:.2f}",
            publishable_key=settings.stripe_publishable_key,
        )

    except Exception as e:
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

        # Log the successful payment
        print(f"Payment succeeded: {payment_intent_id}")
        print(f"Booking reference: {booking_reference}")
        print(f"Amount: £{data['amount'] / 100:.2f}")

        # Update payment status in database (this also updates booking to CONFIRMED)
        db_service.update_payment_status(
            db=db,
            stripe_payment_intent_id=payment_intent_id,
            status=PaymentStatus.SUCCEEDED,
            paid_at=datetime.utcnow(),
        )

        # Book the slot on the departure flight (now that payment succeeded)
        if departure_id and drop_off_slot:
            try:
                departure = db.query(FlightDeparture).filter(
                    FlightDeparture.id == int(departure_id)
                ).first()
                if departure:
                    # Slot "165" = 2¾ hours before = slot 1
                    # Slot "120" = 2 hours before = slot 2
                    if drop_off_slot == "165":
                        departure.is_slot_1_booked = True
                        print(f"Booked slot 1 for departure {departure_id}")
                    elif drop_off_slot == "120":
                        departure.is_slot_2_booked = True
                        print(f"Booked slot 2 for departure {departure_id}")
                    db.commit()
            except Exception as e:
                print(f"Error booking slot: {e}")

        return {"status": "success", "booking_reference": booking_reference}

    elif event_type == "payment_intent.payment_failed":
        payment_intent_id = data["id"]
        error_message = data.get("last_payment_error", {}).get("message", "Unknown error")

        print(f"Payment failed: {payment_intent_id}")
        print(f"Error: {error_message}")

        # Update payment status to failed
        db_service.update_payment_status(
            db=db,
            stripe_payment_intent_id=payment_intent_id,
            status=PaymentStatus.FAILED,
        )

        return {"status": "failed", "error": error_message}

    elif event_type == "charge.refunded":
        charge_id = data["id"]
        refund_amount = data.get("amount_refunded", 0)

        print(f"Refund processed: {charge_id}")
        print(f"Amount refunded: £{refund_amount / 100:.2f}")

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
                    is_slot_1_booked=False,
                    is_slot_2_booked=False,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
