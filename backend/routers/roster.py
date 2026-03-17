"""
Roster & Staff Management API endpoints.

This module provides endpoints for:
- Employee management (CRUD operations on users where is_admin=False)
- Roster shifts CRUD
- Auto-assign shifts from bookings
- Employee-facing read-only shift view
"""

from datetime import date as date_type, time, datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from db_models import User, Booking, RosterShift, ShiftType, ShiftStatus, Session as DbSession, BookingStatus
from models import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    RosterShiftCreate, RosterShiftUpdate, RosterShiftResponse,
    AutoAssignRequest, AutoAssignResponse, OperationalWarning,
    ShiftTypeEnum, ShiftStatusEnum
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter(prefix="/api", tags=["roster"])


# ============================================================================
# Helper Functions
# ============================================================================

def parse_time_string(time_str: str) -> time:
    """Parse HH:MM string to time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def format_time(t: time) -> str:
    """Format time object to HH:MM string."""
    return t.strftime("%H:%M")


def get_staff_initials(user: User) -> str:
    """Get staff initials from user object."""
    if user:
        return f"{user.first_name[0]}{user.last_name[0]}".upper()
    return None


def check_shift_overlap(
    db: Session,
    staff_id: int,
    date: date_type,
    start_time: time,
    end_time: time,
    exclude_shift_id: Optional[int] = None
) -> Optional[RosterShift]:
    """
    Check if a shift overlaps with existing shifts for the same staff member.
    Returns the conflicting shift if found, None otherwise.
    """
    if not staff_id:
        return None  # Unassigned shifts don't conflict

    query = db.query(RosterShift).filter(
        RosterShift.staff_id == staff_id,
        RosterShift.date == date
    )

    if exclude_shift_id:
        query = query.filter(RosterShift.id != exclude_shift_id)

    existing_shifts = query.all()

    for shift in existing_shifts:
        # Check for overlap
        # Overlap occurs if: start1 < end2 AND start2 < end1
        if start_time < shift.end_time and shift.start_time < end_time:
            return shift

    return None


def validate_staff_assignment(db: Session, staff_id: int) -> User:
    """
    Validate that staff_id refers to a valid active user (admin or employee).
    Raises HTTPException if invalid.
    """
    user = db.query(User).filter(User.id == staff_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Staff member not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Cannot assign shift to inactive user")
    return user


def shift_to_response(shift: RosterShift, db: Session) -> RosterShiftResponse:
    """Convert RosterShift model to response."""
    booking_ref = None
    booking_type = None
    booking_customer_name = None
    booking_time = None
    booking_flight_number = None
    booking_destination = None

    if shift.booking_id:
        booking = db.query(Booking).filter(Booking.id == shift.booking_id).first()
        if booking:
            booking_ref = booking.reference
            booking_customer_name = f"{booking.customer_first_name} {booking.customer_last_name}"

            # Determine if this is a dropoff or pickup based on the shift date
            if booking.dropoff_date == shift.date:
                booking_type = "dropoff"
                booking_time = booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else None
                booking_flight_number = booking.dropoff_flight_number
                booking_destination = booking.dropoff_destination
            elif booking.pickup_date == shift.date:
                booking_type = "pickup"
                booking_time = booking.pickup_time.strftime("%H:%M") if booking.pickup_time else None
                booking_flight_number = booking.pickup_flight_number
                booking_destination = booking.pickup_origin

    return RosterShiftResponse(
        id=shift.id,
        staff_id=shift.staff_id,
        staff_first_name=shift.staff.first_name if shift.staff else None,
        staff_last_name=shift.staff.last_name if shift.staff else None,
        staff_initials=get_staff_initials(shift.staff) if shift.staff else None,
        booking_id=shift.booking_id,
        booking_reference=booking_ref,
        booking_type=booking_type,
        booking_customer_name=booking_customer_name,
        booking_time=booking_time,
        booking_flight_number=booking_flight_number,
        booking_destination=booking_destination,
        date=shift.date,
        start_time=format_time(shift.start_time),
        end_time=format_time(shift.end_time),
        shift_type=shift.shift_type.value,
        status=shift.status.value,
        notes=shift.notes,
        created_at=shift.created_at,
        updated_at=shift.updated_at
    )


# ============================================================================
# Dependency: Authentication
# ============================================================================

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


# ============================================================================
# Staff/User Endpoints (Admin Only)
# ============================================================================

@router.get("/staff", response_model=List[EmployeeResponse])
async def list_all_staff(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """
    List ALL users (both admins and employees) for shift assignment.
    Optionally filter by is_active status.
    """
    query = db.query(User)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    users = query.order_by(User.first_name, User.last_name).all()
    return [EmployeeResponse.model_validate(user) for user in users]


# ============================================================================
# Employee Management Endpoints (Admin Only)
# ============================================================================

@router.get("/employees", response_model=List[EmployeeResponse])
async def list_employees(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """
    List all employee users (is_admin = False).
    Optionally filter by is_active status.
    """
    query = db.query(User).filter(User.is_admin == False)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    employees = query.order_by(User.first_name, User.last_name).all()
    return [EmployeeResponse.model_validate(emp) for emp in employees]


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    db: Session = Depends(get_db)
):
    """Get a single employee by ID."""
    employee = db.query(User).filter(
        User.id == employee_id,
        User.is_admin == False
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    return EmployeeResponse.model_validate(employee)


@router.post("/employees", response_model=EmployeeResponse, status_code=201)
async def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new employee user (is_admin = False).
    Email must be unique (case-insensitive).
    """
    # Check for duplicate email (case-insensitive)
    existing = db.query(User).filter(
        User.email.ilike(employee.email)
    ).first()

    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")

    # Validate UK phone number (basic validation)
    phone = employee.phone.strip()
    if not (phone.startswith("+44") or phone.startswith("07") or phone.startswith("01")):
        raise HTTPException(status_code=400, detail="Invalid UK phone number")

    new_employee = User(
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email.lower(),
        phone=phone,
        is_admin=False,
        is_active=True
    )

    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)

    return EmployeeResponse.model_validate(new_employee)


@router.put("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    updates: EmployeeUpdate,
    db: Session = Depends(get_db)
):
    """Update an employee's details."""
    employee = db.query(User).filter(
        User.id == employee_id,
        User.is_admin == False
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check for email conflict if email is being changed
    if updates.email and updates.email.lower() != employee.email:
        existing = db.query(User).filter(
            User.email.ilike(updates.email),
            User.id != employee_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already exists")

    # Apply updates
    if updates.first_name is not None:
        employee.first_name = updates.first_name
    if updates.last_name is not None:
        employee.last_name = updates.last_name
    if updates.email is not None:
        employee.email = updates.email.lower()
    if updates.phone is not None:
        employee.phone = updates.phone

    db.commit()
    db.refresh(employee)

    return EmployeeResponse.model_validate(employee)


@router.delete("/employees/{employee_id}")
async def deactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db)
):
    """
    Soft-deactivate an employee (sets is_active = False).
    Never hard deletes - employee records are preserved.
    """
    employee = db.query(User).filter(
        User.id == employee_id,
        User.is_admin == False
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.is_active = False
    db.commit()

    return {"success": True, "message": f"Employee {employee.first_name} {employee.last_name} deactivated"}


@router.post("/employees/{employee_id}/reactivate")
async def reactivate_employee(
    employee_id: int,
    db: Session = Depends(get_db)
):
    """Reactivate a deactivated employee."""
    employee = db.query(User).filter(
        User.id == employee_id,
        User.is_admin == False
    ).first()

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.is_active = True
    db.commit()

    return {"success": True, "message": f"Employee {employee.first_name} {employee.last_name} reactivated"}


# ============================================================================
# Roster Shifts CRUD Endpoints (Admin Only)
# ============================================================================

@router.get("/roster", response_model=List[RosterShiftResponse])
async def list_shifts(
    date: Optional[date_type] = Query(None, description="Filter by specific date (YYYY-MM-DD)"),
    date_from: Optional[date_type] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date_type] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    staff_id: Optional[int] = Query(None, description="Filter by staff member"),
    week_start: Optional[date_type] = Query(None, description="Filter by week starting date (Mon-Sun)"),
    db: Session = Depends(get_db)
):
    """
    List roster shifts with optional filters.
    - date: Filter by specific date
    - date_from/date_to: Filter by date range
    - staff_id: Filter by staff member
    - week_start: Filter by week (Mon-Sun starting from this date)
    """
    query = db.query(RosterShift)

    if date:
        query = query.filter(RosterShift.date == date)
    elif date_from and date_to:
        query = query.filter(
            RosterShift.date >= date_from,
            RosterShift.date <= date_to
        )
    elif week_start:
        week_end = week_start + timedelta(days=6)
        query = query.filter(
            RosterShift.date >= week_start,
            RosterShift.date <= week_end
        )

    if staff_id:
        query = query.filter(RosterShift.staff_id == staff_id)

    shifts = query.order_by(RosterShift.date, RosterShift.start_time).all()

    return [shift_to_response(shift, db) for shift in shifts]


# ============================================================================
# Bookings for Shift Assignment (must be before /roster/{shift_id})
# ============================================================================

@router.get("/roster/bookings-for-date")
async def get_bookings_for_date(
    date: date_type = Query(..., description="Date to fetch bookings for (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Get bookings that have a drop-off or pickup on the specified date.
    Used for linking shifts to specific bookings.

    Returns bookings with:
    - id, reference
    - type: 'dropoff' or 'pickup'
    - time: the dropoff_time or pickup_time
    - customer name
    - flight details
    """
    results = []

    # Find bookings with dropoff on this date
    dropoff_bookings = db.query(Booking).filter(
        Booking.dropoff_date == date,
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING])
    ).all()

    for b in dropoff_bookings:
        results.append({
            "id": b.id,
            "reference": b.reference or "",
            "type": "dropoff",
            "time": b.dropoff_time.strftime("%H:%M") if b.dropoff_time else None,
            "flight_time": b.flight_departure_time.strftime("%H:%M") if b.flight_departure_time else None,
            "customer_name": f"{b.customer_first_name or ''} {b.customer_last_name or ''}".strip(),
            "flight_number": b.dropoff_flight_number,
            "airline": b.dropoff_airline_name,
            "destination": b.dropoff_destination
        })

    # Find bookings with pickup on this date
    pickup_bookings = db.query(Booking).filter(
        Booking.pickup_date == date,
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING])
    ).all()

    for b in pickup_bookings:
        results.append({
            "id": b.id,
            "reference": b.reference or "",
            "type": "pickup",
            "time": b.pickup_time.strftime("%H:%M") if b.pickup_time else None,
            "flight_time": b.flight_arrival_time.strftime("%H:%M") if b.flight_arrival_time else None,
            "customer_name": f"{b.customer_first_name or ''} {b.customer_last_name or ''}".strip(),
            "flight_number": b.pickup_flight_number,
            "airline": b.pickup_airline_name,
            "origin": b.pickup_origin
        })

    # Sort by time
    results.sort(key=lambda x: x["time"] or "99:99")

    return results


@router.get("/roster/{shift_id}", response_model=RosterShiftResponse)
async def get_shift(
    shift_id: int,
    db: Session = Depends(get_db)
):
    """Get a single roster shift by ID."""
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    return shift_to_response(shift, db)


@router.post("/roster", response_model=RosterShiftResponse, status_code=201)
async def create_shift(
    shift_data: RosterShiftCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new roster shift.
    Validates:
    - Staff must be active employee (not admin)
    - No overlapping shifts for the same staff member
    - Booking must exist if booking_id provided
    """
    start_time = parse_time_string(shift_data.start_time)
    end_time = parse_time_string(shift_data.end_time)

    # Validate staff assignment
    if shift_data.staff_id:
        validate_staff_assignment(db, shift_data.staff_id)

        # Check for overlap
        conflicting = check_shift_overlap(
            db, shift_data.staff_id, shift_data.date, start_time, end_time
        )
        if conflicting:
            raise HTTPException(
                status_code=409,
                detail=f"Shift overlaps with existing shift ({format_time(conflicting.start_time)}-{format_time(conflicting.end_time)})"
            )

    # Validate booking exists if provided
    if shift_data.booking_id:
        booking = db.query(Booking).filter(Booking.id == shift_data.booking_id).first()
        if not booking:
            raise HTTPException(status_code=400, detail="Booking not found")

    # Create shift
    new_shift = RosterShift(
        staff_id=shift_data.staff_id,
        booking_id=shift_data.booking_id,
        date=shift_data.date,
        start_time=start_time,
        end_time=end_time,
        shift_type=ShiftType(shift_data.shift_type.value),
        status=ShiftStatus(shift_data.status.value),
        notes=shift_data.notes
    )

    db.add(new_shift)
    db.commit()
    db.refresh(new_shift)

    return shift_to_response(new_shift, db)


@router.put("/roster/{shift_id}", response_model=RosterShiftResponse)
async def update_shift(
    shift_id: int,
    updates: RosterShiftUpdate,
    db: Session = Depends(get_db)
):
    """Update a roster shift."""
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    # Parse times if provided
    new_start = parse_time_string(updates.start_time) if updates.start_time else shift.start_time
    new_end = parse_time_string(updates.end_time) if updates.end_time else shift.end_time
    new_date = updates.date if updates.date else shift.date
    new_staff_id = updates.staff_id if updates.staff_id is not None else shift.staff_id

    # Validate staff assignment if changing
    if new_staff_id and new_staff_id != shift.staff_id:
        validate_staff_assignment(db, new_staff_id)

    # Check for overlap if staff, date, or times are changing
    if new_staff_id:
        conflicting = check_shift_overlap(
            db, new_staff_id, new_date, new_start, new_end, exclude_shift_id=shift_id
        )
        if conflicting:
            raise HTTPException(
                status_code=409,
                detail=f"Shift overlaps with existing shift ({format_time(conflicting.start_time)}-{format_time(conflicting.end_time)})"
            )

    # Apply updates
    if updates.staff_id is not None:
        shift.staff_id = updates.staff_id
    if updates.booking_id is not None:
        shift.booking_id = updates.booking_id
    if updates.date is not None:
        shift.date = updates.date
    if updates.start_time is not None:
        shift.start_time = new_start
    if updates.end_time is not None:
        shift.end_time = new_end
    if updates.shift_type is not None:
        shift.shift_type = ShiftType(updates.shift_type.value)
    if updates.status is not None:
        shift.status = ShiftStatus(updates.status.value)
    if updates.notes is not None:
        shift.notes = updates.notes

    db.commit()
    db.refresh(shift)

    return shift_to_response(shift, db)


@router.delete("/roster/{shift_id}")
async def delete_shift(
    shift_id: int,
    db: Session = Depends(get_db)
):
    """Delete a roster shift (hard delete)."""
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()

    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    db.delete(shift)
    db.commit()

    return {"success": True, "message": "Shift deleted"}


# ============================================================================
# Auto-Assign Endpoint (Admin Only)
# ============================================================================

@router.post("/roster/auto-assign", response_model=AutoAssignResponse)
async def auto_assign_shifts(
    request: AutoAssignRequest,
    db: Session = Depends(get_db)
):
    """
    Auto-generate roster shifts from bookings in the date range.

    For each booking:
    - Creates a 'departure' shift on dropoff_date (2-2.5 hours before flight)
    - Creates an 'arrival' shift on pickup_date (45-60 min after arrival)

    Shifts are created as unassigned (staff_id = null) with status 'scheduled'.
    Admin manually assigns staff afterwards.
    """
    shifts_deleted = 0
    shifts_created = 0
    created_shifts = []

    # Optionally clear existing scheduled shifts
    if request.clear_existing:
        deleted = db.query(RosterShift).filter(
            RosterShift.date >= request.date_from,
            RosterShift.date <= request.date_to,
            RosterShift.status == ShiftStatus.SCHEDULED
        ).delete()
        shifts_deleted = deleted

    # Find bookings with dropoff or pickup in the date range
    bookings = db.query(Booking).filter(
        or_(
            and_(
                Booking.dropoff_date >= request.date_from,
                Booking.dropoff_date <= request.date_to
            ),
            and_(
                Booking.pickup_date >= request.date_from,
                Booking.pickup_date <= request.date_to
            )
        ),
        Booking.status.in_(["confirmed", "pending"])
    ).all()

    for booking in bookings:
        # Create departure shift if dropoff is in range
        if request.date_from <= booking.dropoff_date <= request.date_to:
            # Calculate shift time: 2.5 hours before flight departure
            if booking.flight_departure_time:
                flight_mins = booking.flight_departure_time.hour * 60 + booking.flight_departure_time.minute
                shift_start_mins = flight_mins - 150  # 2.5 hours before
                shift_end_mins = flight_mins - 105  # 1.75 hours before (45 min shift)

                # Handle overnight
                if shift_start_mins < 0:
                    shift_start_mins += 24 * 60
                if shift_end_mins < 0:
                    shift_end_mins += 24 * 60

                start_time = time(shift_start_mins // 60, shift_start_mins % 60)
                end_time = time(shift_end_mins // 60, shift_end_mins % 60)

                # Build notes
                notes_parts = []
                if booking.customer_first_name and booking.customer_last_name:
                    notes_parts.append(f"{booking.customer_first_name} {booking.customer_last_name}")
                if booking.dropoff_airline_name and booking.dropoff_destination:
                    notes_parts.append(f"{booking.dropoff_airline_name} to {booking.dropoff_destination}")

                # Determine shift type based on start time
                shift_hour = start_time.hour
                if shift_hour < 7:
                    shift_type = ShiftType.EARLY_MORNING
                elif shift_hour < 11:
                    shift_type = ShiftType.MORNING
                elif shift_hour < 14:
                    shift_type = ShiftType.MIDDAY
                elif shift_hour < 17 or (shift_hour == 17 and start_time.minute < 30):
                    shift_type = ShiftType.AFTERNOON
                elif shift_hour < 21:
                    shift_type = ShiftType.LATE_AFTERNOON
                else:
                    shift_type = ShiftType.EVENING

                dep_shift = RosterShift(
                    staff_id=None,
                    booking_id=booking.id,
                    date=booking.dropoff_date,
                    start_time=start_time,
                    end_time=end_time,
                    shift_type=shift_type,
                    status=ShiftStatus.SCHEDULED,
                    notes=" — ".join(notes_parts) if notes_parts else None
                )
                db.add(dep_shift)
                created_shifts.append(dep_shift)
                shifts_created += 1

        # Create arrival shift if pickup is in range
        if request.date_from <= booking.pickup_date <= request.date_to:
            # Calculate shift time: 45 min after flight arrival
            if booking.flight_arrival_time:
                arrival_mins = booking.flight_arrival_time.hour * 60 + booking.flight_arrival_time.minute
                shift_start_mins = arrival_mins + 45  # 45 min after arrival
                shift_end_mins = shift_start_mins + 30  # 30 min shift

                # Handle overnight
                shift_start_mins = shift_start_mins % (24 * 60)
                shift_end_mins = shift_end_mins % (24 * 60)

                start_time = time(shift_start_mins // 60, shift_start_mins % 60)
                end_time = time(shift_end_mins // 60, shift_end_mins % 60)

                # Build notes
                notes_parts = []
                if booking.customer_first_name and booking.customer_last_name:
                    notes_parts.append(f"{booking.customer_first_name} {booking.customer_last_name}")
                notes_parts.append("return")

                # Determine shift type based on start time
                shift_hour = start_time.hour
                if shift_hour < 7:
                    shift_type = ShiftType.EARLY_MORNING
                elif shift_hour < 11:
                    shift_type = ShiftType.MORNING
                elif shift_hour < 14:
                    shift_type = ShiftType.MIDDAY
                elif shift_hour < 17 or (shift_hour == 17 and start_time.minute < 30):
                    shift_type = ShiftType.AFTERNOON
                elif shift_hour < 21:
                    shift_type = ShiftType.LATE_AFTERNOON
                else:
                    shift_type = ShiftType.EVENING

                arr_shift = RosterShift(
                    staff_id=None,
                    booking_id=booking.id,
                    date=booking.pickup_date,
                    start_time=start_time,
                    end_time=end_time,
                    shift_type=shift_type,
                    status=ShiftStatus.SCHEDULED,
                    notes=" — ".join(notes_parts) if notes_parts else None
                )
                db.add(arr_shift)
                created_shifts.append(arr_shift)
                shifts_created += 1

    db.commit()

    # Refresh and convert to response
    for shift in created_shifts:
        db.refresh(shift)

    return AutoAssignResponse(
        success=True,
        shifts_created=shifts_created,
        shifts_deleted=shifts_deleted,
        shifts=[shift_to_response(s, db) for s in created_shifts]
    )


# ============================================================================
# Employee Page - Read-Only Shift View
# ============================================================================

@router.get("/employee/shifts", response_model=List[RosterShiftResponse])
async def get_employee_shifts(
    date_from: Optional[date_type] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date_type] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    week_start: Optional[date_type] = Query(None, description="Filter by week starting date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get shifts for the authenticated user (read-only).
    Returns only the logged-in user's shifts.
    Works for both employees and admins viewing their own shifts.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Employee shifts request: user_id={current_user.id}, email={current_user.email}")

    query = db.query(RosterShift).filter(RosterShift.staff_id == current_user.id)

    # Debug: count all shifts for this user
    all_user_shifts = query.count()
    logger.info(f"Total shifts for user {current_user.id}: {all_user_shifts}")

    # Apply date filters
    if date_from and date_to:
        query = query.filter(
            RosterShift.date >= date_from,
            RosterShift.date <= date_to
        )
    elif week_start:
        week_end = week_start + timedelta(days=6)
        query = query.filter(
            RosterShift.date >= week_start,
            RosterShift.date <= week_end
        )

    shifts = query.order_by(RosterShift.date, RosterShift.start_time).all()

    return [shift_to_response(shift, db) for shift in shifts]


# ============================================================================
# CSV Export (Admin Only)
# ============================================================================

@router.get("/roster/export")
async def export_roster_csv(
    week_start: date_type = Query(..., description="Start date for export"),
    db: Session = Depends(get_db)
):
    """
    Export roster shifts as CSV.
    Dates formatted as DD/MM/YYYY, times as HH:MM.
    """
    from fastapi.responses import StreamingResponse
    import csv
    import io

    week_end = week_start + timedelta(days=6)

    shifts = db.query(RosterShift).filter(
        RosterShift.date >= week_start,
        RosterShift.date <= week_end
    ).order_by(RosterShift.date, RosterShift.start_time).all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Date", "Employee Name", "Shift Type", "Start Time", "End Time",
        "Booking Ref", "Status", "Notes"
    ])

    for shift in shifts:
        # Get booking reference
        booking_ref = ""
        if shift.booking_id:
            booking = db.query(Booking).filter(Booking.id == shift.booking_id).first()
            if booking:
                booking_ref = booking.reference

        # Format employee name
        employee_name = "Unassigned"
        if shift.staff:
            employee_name = f"{shift.staff.first_name} {shift.staff.last_name}"

        writer.writerow([
            shift.date.strftime("%d/%m/%Y"),
            employee_name,
            shift.shift_type.value.capitalize(),
            shift.start_time.strftime("%H:%M"),
            shift.end_time.strftime("%H:%M"),
            booking_ref,
            shift.status.value.capitalize(),
            shift.notes or ""
        ])

    output.seek(0)

    filename = f"roster_export_{week_start.strftime('%d%m%Y')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
