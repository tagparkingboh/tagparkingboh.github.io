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
from db_models import User, Booking, RosterShift, ShiftType, ShiftStatus, Session as DbSession, BookingStatus, ShiftBookingLink
from models import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    RosterShiftCreate, RosterShiftUpdate, RosterShiftResponse,
    AutoAssignRequest, AutoAssignResponse, OperationalWarning,
    ShiftTypeEnum, ShiftStatusEnum, LinkedBookingInfo
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
    Handles overnight shifts where end_time < start_time.
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

    def time_to_minutes(t: time, is_overnight_end: bool = False) -> int:
        """Convert time to minutes, adding 24 hours for overnight end times."""
        mins = t.hour * 60 + t.minute
        if is_overnight_end:
            mins += 24 * 60
        return mins

    # Convert new shift times to minutes
    new_start_mins = time_to_minutes(start_time)
    new_is_overnight = end_time < start_time
    new_end_mins = time_to_minutes(end_time, is_overnight_end=new_is_overnight)

    for shift in existing_shifts:
        # Convert existing shift times to minutes
        existing_start_mins = time_to_minutes(shift.start_time)
        existing_is_overnight = shift.end_time < shift.start_time
        existing_end_mins = time_to_minutes(shift.end_time, is_overnight_end=existing_is_overnight)

        # Check for overlap: start1 < end2 AND start2 < end1
        if new_start_mins < existing_end_mins and existing_start_mins < new_end_mins:
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
    # Build list of linked bookings
    linked_bookings = []

    # For overnight shifts, check both start date and end date
    shift_dates = {shift.date}
    if shift.end_date and shift.end_date != shift.date:
        shift_dates.add(shift.end_date)

    # Get bookings from many-to-many relationship
    for booking in shift.bookings:
        # Determine if this is a dropoff or pickup based on shift dates
        if booking.dropoff_date in shift_dates:
            linked_bookings.append(LinkedBookingInfo(
                id=booking.id,
                reference=booking.reference or "",
                type="dropoff",
                customer_name=f"{booking.customer_first_name or ''} {booking.customer_last_name or ''}".strip(),
                time=booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else None,
                flight_number=booking.dropoff_flight_number,
                destination=booking.dropoff_destination
            ))
        elif booking.pickup_date in shift_dates:
            linked_bookings.append(LinkedBookingInfo(
                id=booking.id,
                reference=booking.reference or "",
                type="pickup",
                customer_name=f"{booking.customer_first_name or ''} {booking.customer_last_name or ''}".strip(),
                time=booking.pickup_time.strftime("%H:%M") if booking.pickup_time else None,
                flight_number=booking.pickup_flight_number,
                destination=booking.pickup_origin
            ))

    # Also check legacy single booking_id (for backwards compatibility)
    if shift.booking_id and not any(b.id == shift.booking_id for b in shift.bookings):
        booking = db.query(Booking).filter(Booking.id == shift.booking_id).first()
        if booking:
            if booking.dropoff_date in shift_dates:
                linked_bookings.append(LinkedBookingInfo(
                    id=booking.id,
                    reference=booking.reference or "",
                    type="dropoff",
                    customer_name=f"{booking.customer_first_name or ''} {booking.customer_last_name or ''}".strip(),
                    time=booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else None,
                    flight_number=booking.dropoff_flight_number,
                    destination=booking.dropoff_destination
                ))
            elif booking.pickup_date in shift_dates:
                linked_bookings.append(LinkedBookingInfo(
                    id=booking.id,
                    reference=booking.reference or "",
                    type="pickup",
                    customer_name=f"{booking.customer_first_name or ''} {booking.customer_last_name or ''}".strip(),
                    time=booking.pickup_time.strftime("%H:%M") if booking.pickup_time else None,
                    flight_number=booking.pickup_flight_number,
                    destination=booking.pickup_origin
                ))

    # For backwards compatibility, populate the single booking fields with first booking
    first_booking = linked_bookings[0] if linked_bookings else None

    return RosterShiftResponse(
        id=shift.id,
        staff_id=shift.staff_id,
        staff_first_name=shift.staff.first_name if shift.staff else None,
        staff_last_name=shift.staff.last_name if shift.staff else None,
        staff_initials=get_staff_initials(shift.staff) if shift.staff else None,
        # Legacy single booking fields (backwards compatibility)
        booking_id=first_booking.id if first_booking else None,
        booking_reference=first_booking.reference if first_booking else None,
        booking_type=first_booking.type if first_booking else None,
        booking_customer_name=first_booking.customer_name if first_booking else None,
        booking_time=first_booking.time if first_booking else None,
        booking_flight_number=first_booking.flight_number if first_booking else None,
        booking_destination=first_booking.destination if first_booking else None,
        # New: all linked bookings
        bookings=linked_bookings,
        date=shift.date,
        end_date=shift.end_date or shift.date,  # Default to date if not set
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


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to require admin privileges.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    return current_user


# ============================================================================
# Weekly Hours Helper Function
# ============================================================================

def calculate_shift_hours(start_time, end_time, is_overnight: bool = False) -> float:
    """
    Calculate hours worked for a shift.
    Handles overnight shifts that cross midnight.
    """
    from datetime import datetime, timedelta as td

    # Create datetime objects for calculation
    start_dt = datetime.combine(datetime.today(), start_time)
    end_dt = datetime.combine(datetime.today(), end_time)

    # If overnight shift or end_time is before start_time, add a day to end
    if is_overnight or end_dt <= start_dt:
        end_dt += td(days=1)

    duration = end_dt - start_dt
    hours = duration.total_seconds() / 3600
    return round(hours, 2)


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
        # Include shifts that start on this date OR overnight shifts that end on this date
        query = query.filter(
            or_(
                RosterShift.date == date,
                RosterShift.end_date == date
            )
        )
    elif date_from and date_to:
        # Include shifts that start in range OR overnight shifts that end in range
        query = query.filter(
            or_(
                and_(RosterShift.date >= date_from, RosterShift.date <= date_to),
                and_(RosterShift.end_date >= date_from, RosterShift.end_date <= date_to)
            )
        )
    elif week_start:
        week_end = week_start + timedelta(days=6)
        # Include shifts that start in week OR overnight shifts that end in week
        query = query.filter(
            or_(
                and_(RosterShift.date >= week_start, RosterShift.date <= week_end),
                and_(RosterShift.end_date >= week_start, RosterShift.end_date <= week_end)
            )
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

    # Find bookings with dropoff on this date (only confirmed - pending means unpaid)
    dropoff_bookings = db.query(Booking).filter(
        Booking.dropoff_date == date,
        Booking.status == BookingStatus.CONFIRMED
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

    # Find bookings with pickup on this date (only confirmed - pending means unpaid)
    pickup_bookings = db.query(Booking).filter(
        Booking.pickup_date == date,
        Booking.status == BookingStatus.CONFIRMED
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


# ============================================================================
# Weekly Hours Endpoint (must be before /roster/{shift_id})
# ============================================================================

@router.get("/roster/weekly-hours")
async def get_weekly_hours(
    week_start: date_type = Query(..., description="Monday of the week (YYYY-MM-DD)"),
    staff_id: Optional[int] = Query(None, description="Filter by specific staff member (admin only)"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get weekly hours worked for all employees (admin view).
    Returns hours breakdown per employee for the specified week (Mon-Sun).
    """
    week_end = week_start + timedelta(days=6)

    # Get all shifts for the week
    query = db.query(RosterShift).filter(
        RosterShift.date >= week_start,
        RosterShift.date <= week_end,
        RosterShift.staff_id.isnot(None)  # Only assigned shifts
    )

    if staff_id:
        query = query.filter(RosterShift.staff_id == staff_id)

    shifts = query.all()

    # Group shifts by employee and calculate hours
    employee_hours = {}
    for shift in shifts:
        if shift.staff_id not in employee_hours:
            # Get employee info
            employee = db.query(User).filter(User.id == shift.staff_id).first()
            if employee:
                employee_hours[shift.staff_id] = {
                    "employee_id": shift.staff_id,
                    "employee_name": f"{employee.first_name or ''} {employee.last_name or ''}".strip() or employee.email,
                    "total_hours": 0.0,
                    "shift_count": 0,
                    "daily_hours": {str(week_start + timedelta(days=i)): 0.0 for i in range(7)}
                }

        if shift.staff_id in employee_hours:
            # Calculate hours for this shift
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

            employee_hours[shift.staff_id]["total_hours"] += hours
            employee_hours[shift.staff_id]["shift_count"] += 1

            # Add to daily breakdown
            date_key = str(shift.date)
            if date_key in employee_hours[shift.staff_id]["daily_hours"]:
                employee_hours[shift.staff_id]["daily_hours"][date_key] += hours

    return {
        "week_start": str(week_start),
        "week_end": str(week_end),
        "employees": list(employee_hours.values())
    }


# ============================================================================
# Monthly Hours Endpoints (for payroll - must be before /roster/{shift_id})
# ============================================================================

@router.get("/roster/monthly-hours")
async def get_monthly_hours(
    year: int = Query(..., description="Year (YYYY)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    staff_id: Optional[int] = Query(None, description="Filter by specific staff member"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get monthly hours worked for all employees (admin view).
    Returns total hours per employee for the specified month.
    Hours are attributed to the shift start date.
    Used for payroll calculations.
    """
    import calendar

    # Calculate month start and end dates
    month_start = date_type(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date_type(year, month, last_day)

    # Get all shifts for the month
    query = db.query(RosterShift).filter(
        RosterShift.date >= month_start,
        RosterShift.date <= month_end,
        RosterShift.staff_id.isnot(None)  # Only assigned shifts
    )

    if staff_id:
        query = query.filter(RosterShift.staff_id == staff_id)

    shifts = query.all()

    # Group shifts by employee and calculate hours
    employee_hours = {}
    for shift in shifts:
        if shift.staff_id not in employee_hours:
            # Get employee info
            employee = db.query(User).filter(User.id == shift.staff_id).first()
            if employee:
                employee_hours[shift.staff_id] = {
                    "employee_id": shift.staff_id,
                    "employee_name": f"{employee.first_name or ''} {employee.last_name or ''}".strip() or employee.email,
                    "total_hours": 0.0,
                    "shift_count": 0,
                }

        if shift.staff_id in employee_hours:
            # Calculate hours for this shift
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

            employee_hours[shift.staff_id]["total_hours"] += hours
            employee_hours[shift.staff_id]["shift_count"] += 1

    # Round total hours for each employee
    for emp_id in employee_hours:
        employee_hours[emp_id]["total_hours"] = round(employee_hours[emp_id]["total_hours"], 2)

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "month_start": str(month_start),
        "month_end": str(month_end),
        "employees": list(employee_hours.values())
    }


@router.get("/employee/monthly-hours")
async def get_employee_monthly_hours(
    year: int = Query(..., description="Year (YYYY)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get monthly hours worked for the authenticated employee.
    Returns total hours for the specified month.
    Employees can only see their own hours.
    """
    import calendar

    # Calculate month start and end dates
    month_start = date_type(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date_type(year, month, last_day)

    # Get shifts for the current user only
    shifts = db.query(RosterShift).filter(
        RosterShift.date >= month_start,
        RosterShift.date <= month_end,
        RosterShift.staff_id == current_user.id
    ).all()

    # Calculate hours
    total_hours = 0.0
    shift_count = 0

    for shift in shifts:
        is_overnight = shift.end_date and shift.end_date != shift.date
        hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

        total_hours += hours
        shift_count += 1

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "month_start": str(month_start),
        "month_end": str(month_end),
        "employee_id": current_user.id,
        "employee_name": f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email,
        "total_hours": round(total_hours, 2),
        "shift_count": shift_count
    }


# ============================================================================
# CSV Export (Admin Only) - must be before /roster/{shift_id}
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

    # Validate bookings exist if provided
    booking_ids_to_link = []
    if shift_data.booking_ids:
        for bid in shift_data.booking_ids:
            booking = db.query(Booking).filter(Booking.id == bid).first()
            if not booking:
                raise HTTPException(status_code=400, detail=f"Booking {bid} not found")
            booking_ids_to_link.append(bid)
    elif shift_data.booking_id:
        # Legacy single booking_id support
        booking = db.query(Booking).filter(Booking.id == shift_data.booking_id).first()
        if not booking:
            raise HTTPException(status_code=400, detail="Booking not found")
        booking_ids_to_link.append(shift_data.booking_id)

    # Create shift
    new_shift = RosterShift(
        staff_id=shift_data.staff_id,
        booking_id=None,  # No longer using single booking_id
        date=shift_data.date,
        end_date=shift_data.end_date or shift_data.date,  # Default to same day
        start_time=start_time,
        end_time=end_time,
        shift_type=ShiftType(shift_data.shift_type.value),
        status=ShiftStatus(shift_data.status.value),
        notes=shift_data.notes
    )

    db.add(new_shift)
    db.flush()  # Get the shift ID before adding links

    # Create booking links
    for bid in booking_ids_to_link:
        link = ShiftBookingLink(shift_id=new_shift.id, booking_id=bid)
        db.add(link)

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
    if updates.date is not None:
        shift.date = updates.date
    if updates.end_date is not None:
        shift.end_date = updates.end_date
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

    # Handle booking links update
    if updates.booking_ids is not None:
        # Validate all booking IDs exist
        for bid in updates.booking_ids:
            booking = db.query(Booking).filter(Booking.id == bid).first()
            if not booking:
                raise HTTPException(status_code=400, detail=f"Booking {bid} not found")

        # Remove existing links
        db.query(ShiftBookingLink).filter(ShiftBookingLink.shift_id == shift_id).delete()

        # Add new links
        for bid in updates.booking_ids:
            link = ShiftBookingLink(shift_id=shift_id, booking_id=bid)
            db.add(link)

        # Clear legacy booking_id
        shift.booking_id = None
    elif updates.booking_id is not None:
        # Legacy single booking support - convert to link
        db.query(ShiftBookingLink).filter(ShiftBookingLink.shift_id == shift_id).delete()
        if updates.booking_id:
            booking = db.query(Booking).filter(Booking.id == updates.booking_id).first()
            if not booking:
                raise HTTPException(status_code=400, detail="Booking not found")
            link = ShiftBookingLink(shift_id=shift_id, booking_id=updates.booking_id)
            db.add(link)
        shift.booking_id = None

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
        Booking.status == BookingStatus.CONFIRMED
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

    # Apply date filters (include overnight shifts that end in range)
    if date_from and date_to:
        query = query.filter(
            or_(
                and_(RosterShift.date >= date_from, RosterShift.date <= date_to),
                and_(RosterShift.end_date >= date_from, RosterShift.end_date <= date_to)
            )
        )
    elif week_start:
        week_end = week_start + timedelta(days=6)
        query = query.filter(
            or_(
                and_(RosterShift.date >= week_start, RosterShift.date <= week_end),
                and_(RosterShift.end_date >= week_start, RosterShift.end_date <= week_end)
            )
        )

    shifts = query.order_by(RosterShift.date, RosterShift.start_time).all()

    return [shift_to_response(shift, db) for shift in shifts]


@router.get("/employee/weekly-hours")
async def get_employee_weekly_hours(
    week_start: date_type = Query(..., description="Monday of the week (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get weekly hours worked for the authenticated employee.
    Returns hours breakdown for the specified week (Mon-Sun).
    Employees can only see their own hours.
    """
    week_end = week_start + timedelta(days=6)

    # Get shifts for the current user only
    shifts = db.query(RosterShift).filter(
        RosterShift.date >= week_start,
        RosterShift.date <= week_end,
        RosterShift.staff_id == current_user.id
    ).all()

    # Calculate hours
    total_hours = 0.0
    shift_count = 0
    daily_hours = {str(week_start + timedelta(days=i)): 0.0 for i in range(7)}

    for shift in shifts:
        is_overnight = shift.end_date and shift.end_date != shift.date
        hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

        total_hours += hours
        shift_count += 1

        date_key = str(shift.date)
        if date_key in daily_hours:
            daily_hours[date_key] += hours

    return {
        "week_start": str(week_start),
        "week_end": str(week_end),
        "employee_id": current_user.id,
        "employee_name": f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email,
        "total_hours": round(total_hours, 2),
        "shift_count": shift_count,
        "daily_hours": daily_hours
    }


# ============================================================================
# Payroll Endpoints (Admin Only)
# ============================================================================

@router.get("/payroll/monthly")
async def get_monthly_payroll(
    year: int = Query(..., description="Year (e.g., 2026)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    db: Session = Depends(get_db)
):
    """
    Get monthly payroll summary for all staff.
    Returns total shifts and hours per staff member for the specified month.
    Shifts are attributed to the month based on their start date.
    """
    from calendar import monthrange

    # Calculate month date range
    first_day = date_type(year, month, 1)
    last_day = date_type(year, month, monthrange(year, month)[1])

    # Get all shifts for the month with staff info
    shifts = db.query(RosterShift).filter(
        RosterShift.date >= first_day,
        RosterShift.date <= last_day,
        RosterShift.staff_id.isnot(None)  # Only assigned shifts
    ).order_by(RosterShift.date, RosterShift.start_time).all()

    # Get all active staff for the summary (even if they have no shifts)
    all_staff = db.query(User).filter(User.is_active == True).order_by(User.first_name, User.last_name).all()

    # Group shifts by staff
    staff_data = {}
    for staff in all_staff:
        staff_data[staff.id] = {
            "staff_id": staff.id,
            "staff_name": f"{staff.first_name or ''} {staff.last_name or ''}".strip() or staff.email,
            "total_shifts": 0,
            "total_hours": 0.0,
            "shifts": []  # Detailed shift list for individual view
        }

    for shift in shifts:
        if shift.staff_id not in staff_data:
            # Staff might be inactive but has historical shifts
            staff = db.query(User).filter(User.id == shift.staff_id).first()
            if staff:
                staff_data[shift.staff_id] = {
                    "staff_id": shift.staff_id,
                    "staff_name": f"{staff.first_name or ''} {staff.last_name or ''}".strip() or staff.email,
                    "total_shifts": 0,
                    "total_hours": 0.0,
                    "shifts": []
                }
            else:
                continue

        is_overnight = shift.end_date and shift.end_date != shift.date
        hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

        staff_data[shift.staff_id]["total_shifts"] += 1
        staff_data[shift.staff_id]["total_hours"] += hours
        staff_data[shift.staff_id]["shifts"].append({
            "id": shift.id,
            "date": str(shift.date),
            "start_time": format_time(shift.start_time),
            "end_time": format_time(shift.end_time),
            "hours": round(hours, 2),
            "is_overnight": is_overnight
        })

    # Round totals and filter out staff with no shifts (optional: keep all for full list)
    result = []
    for staff_id, data in staff_data.items():
        data["total_hours"] = round(data["total_hours"], 2)
        # Group shifts by date for the individual view
        shifts_by_date = {}
        for shift in data["shifts"]:
            date_key = shift["date"]
            if date_key not in shifts_by_date:
                shifts_by_date[date_key] = {
                    "date": date_key,
                    "shifts": [],
                    "daily_hours": 0.0
                }
            shifts_by_date[date_key]["shifts"].append(shift)
            shifts_by_date[date_key]["daily_hours"] += shift["hours"]

        # Round daily hours and sort by date
        for date_data in shifts_by_date.values():
            date_data["daily_hours"] = round(date_data["daily_hours"], 2)

        data["shifts_by_date"] = sorted(shifts_by_date.values(), key=lambda x: x["date"])
        del data["shifts"]  # Remove flat list, use grouped version

        result.append(data)

    # Sort by name
    result.sort(key=lambda x: x["staff_name"])

    return {
        "year": year,
        "month": month,
        "month_name": first_day.strftime("%B"),
        "staff": result,
        "totals": {
            "total_staff_with_shifts": len([s for s in result if s["total_shifts"] > 0]),
            "total_shifts": sum(s["total_shifts"] for s in result),
            "total_hours": round(sum(s["total_hours"] for s in result), 2)
        }
    }


@router.get("/employee/payroll/monthly")
async def get_employee_monthly_payroll(
    year: int = Query(..., description="Year (e.g., 2026)"),
    month: int = Query(..., ge=1, le=12, description="Month (1-12)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get monthly payroll for the authenticated employee.
    Returns total shifts and hours for the current user only.
    """
    from calendar import monthrange

    # Calculate month date range
    first_day = date_type(year, month, 1)
    last_day = date_type(year, month, monthrange(year, month)[1])

    # Get shifts for the current user only
    shifts = db.query(RosterShift).filter(
        RosterShift.date >= first_day,
        RosterShift.date <= last_day,
        RosterShift.staff_id == current_user.id
    ).order_by(RosterShift.date, RosterShift.start_time).all()

    # Calculate totals and group by date
    total_hours = 0.0
    total_shifts = 0
    shifts_by_date = {}

    for shift in shifts:
        is_overnight = shift.end_date and shift.end_date != shift.date
        hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)

        total_hours += hours
        total_shifts += 1

        date_key = str(shift.date)
        if date_key not in shifts_by_date:
            shifts_by_date[date_key] = {
                "date": date_key,
                "shifts": [],
                "daily_hours": 0.0
            }

        shifts_by_date[date_key]["shifts"].append({
            "id": shift.id,
            "start_time": format_time(shift.start_time),
            "end_time": format_time(shift.end_time),
            "hours": round(hours, 2),
            "is_overnight": is_overnight
        })
        shifts_by_date[date_key]["daily_hours"] += hours

    # Round daily hours
    for date_data in shifts_by_date.values():
        date_data["daily_hours"] = round(date_data["daily_hours"], 2)

    return {
        "year": year,
        "month": month,
        "month_name": first_day.strftime("%B"),
        "employee_id": current_user.id,
        "employee_name": f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email,
        "total_shifts": total_shifts,
        "total_hours": round(total_hours, 2),
        "shifts_by_date": sorted(shifts_by_date.values(), key=lambda x: x["date"])
    }
