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
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from db_models import User, Booking, RosterShift, ShiftType, ShiftStatus, Session as DbSession, BookingStatus, ShiftBookingLink, EmployeeHoliday, HolidayType, RosterPlannerSettings as DbRosterPlannerSettings
from models import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    RosterShiftCreate, RosterShiftUpdate, RosterShiftResponse,
    AutoAssignRequest, AutoAssignResponse, OperationalWarning,
    ShiftTypeEnum, ShiftStatusEnum, LinkedBookingInfo,
    RosterPlannerSettingsResponse, RosterPlannerSettingsUpdate,
    RosterProposalResponse,
    PlannerRunListItem, PlannerRunDetail,
    PlannerRunFeedbackCreate, PlannerRunFeedbackResponse,
)
from roster_planner import propose_roster, PlannerSettings, UK_TZ
from roster_planner_runner import (
    fire_engine_async,
    record_run,
    TRIGGER_HOLIDAY_CHANGED,
    TRIGGER_MANUAL,
    TRIGGER_SETTINGS_CHANGED,
)
import json
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


def check_holiday_time_overlap(
    existing_start_time: Optional[time],
    existing_end_time: Optional[time],
    new_start_time: Optional[time],
    new_end_time: Optional[time]
) -> bool:
    """
    Check if two holiday/unavailability entries have overlapping times.

    Rules:
    - If either entry is full day (no times), they overlap
    - If both have times, check if the time ranges overlap

    Returns True if they overlap, False if they don't.
    """
    # If existing entry is full day (no times), it covers entire day → overlap
    if existing_start_time is None or existing_end_time is None:
        return True

    # If new entry is full day (no times), it covers entire day → overlap
    if new_start_time is None or new_end_time is None:
        return True

    # Both have times - check if time ranges overlap
    # Overlap if: new_start < existing_end AND new_end > existing_start
    return new_start_time < existing_end_time and new_end_time > existing_start_time


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


def check_staff_unavailability(
    db: Session,
    staff_id: int,
    shift_date: date_type,
    shift_start: time,
    shift_end: time
) -> Optional[EmployeeHoliday]:
    """
    Check if staff member is marked as unavailable during the shift time.

    Returns the conflicting unavailability record if found, None otherwise.
    Checks both full-day unavailability and partial-day with time ranges.
    """
    if not staff_id:
        return None  # Unassigned shifts don't need unavailability check

    # Find any unavailability records for this staff on this date
    unavailabilities = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.staff_id == staff_id,
        EmployeeHoliday.holiday_type == HolidayType.UNAVAILABLE,
        EmployeeHoliday.start_date <= shift_date,
        EmployeeHoliday.end_date >= shift_date
    ).all()

    for unavail in unavailabilities:
        # If no times specified, it's a full-day unavailability - conflicts with any shift
        if unavail.start_time is None and unavail.end_time is None:
            return unavail

        # If times are specified, check for overlap
        if unavail.start_time and unavail.end_time:
            # Convert to minutes for comparison
            def time_to_mins(t: time) -> int:
                return t.hour * 60 + t.minute

            unavail_start = time_to_mins(unavail.start_time)
            unavail_end = time_to_mins(unavail.end_time)
            shift_start_mins = time_to_mins(shift_start)
            shift_end_mins = time_to_mins(shift_end)

            # Handle overnight shifts
            if shift_end < shift_start:
                shift_end_mins += 24 * 60

            # Handle overnight unavailability
            if unavail.end_time < unavail.start_time:
                unavail_end += 24 * 60

            # Check for overlap
            if shift_start_mins < unavail_end and unavail_start < shift_end_mins:
                return unavail

    return None


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
    Returns total hours per employee for the specified month, with weekly breakdown.
    Hours are attributed to the shift start date.
    Weeks run Monday-Sunday.
    Used for payroll calculations.
    """
    import calendar
    from datetime import timedelta

    # Calculate month start and end dates
    month_start = date_type(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date_type(year, month, last_day)

    # Calculate weeks in the month (Mon-Sun)
    weeks = []
    current = month_start
    # Find the Monday of the first week (may be in previous month)
    week_start = current - timedelta(days=current.weekday())

    while week_start <= month_end:
        week_end = week_start + timedelta(days=6)
        # Only include weeks that overlap with this month
        if week_end >= month_start:
            weeks.append({
                "week_start": max(week_start, month_start),
                "week_end": min(week_end, month_end),
                "week_start_display": week_start,  # For display purposes
                "week_end_display": week_end,
            })
        week_start = week_start + timedelta(days=7)

    # Get all shifts for the month
    query = db.query(RosterShift).filter(
        RosterShift.date >= month_start,
        RosterShift.date <= month_end,
        RosterShift.staff_id.isnot(None)  # Only assigned shifts
    )

    if staff_id:
        query = query.filter(RosterShift.staff_id == staff_id)

    shifts = query.all()

    # Build employee info cache
    employee_info = {}
    for shift in shifts:
        if shift.staff_id not in employee_info:
            employee = db.query(User).filter(User.id == shift.staff_id).first()
            if employee:
                employee_info[shift.staff_id] = {
                    "employee_id": shift.staff_id,
                    "employee_name": f"{employee.first_name or ''} {employee.last_name or ''}".strip() or employee.email,
                }

    # Group shifts by employee and calculate total hours
    employee_totals = {}
    for shift in shifts:
        if shift.staff_id not in employee_totals:
            if shift.staff_id in employee_info:
                employee_totals[shift.staff_id] = {
                    **employee_info[shift.staff_id],
                    "total_hours": 0.0,
                    "shift_count": 0,
                }

        if shift.staff_id in employee_totals:
            is_overnight = shift.end_date and shift.end_date != shift.date
            hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
            employee_totals[shift.staff_id]["total_hours"] += hours
            employee_totals[shift.staff_id]["shift_count"] += 1

    # Calculate weekly breakdown
    weeks_data = []
    for week_idx, week in enumerate(weeks):
        week_employee_hours = {}

        for shift in shifts:
            if week["week_start"] <= shift.date <= week["week_end"]:
                if shift.staff_id not in week_employee_hours:
                    if shift.staff_id in employee_info:
                        week_employee_hours[shift.staff_id] = {
                            **employee_info[shift.staff_id],
                            "total_hours": 0.0,
                            "shift_count": 0,
                        }

                if shift.staff_id in week_employee_hours:
                    is_overnight = shift.end_date and shift.end_date != shift.date
                    hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
                    week_employee_hours[shift.staff_id]["total_hours"] += hours
                    week_employee_hours[shift.staff_id]["shift_count"] += 1

        # Round hours for this week
        for emp_id in week_employee_hours:
            week_employee_hours[emp_id]["total_hours"] = round(week_employee_hours[emp_id]["total_hours"], 2)

        # Format week label (handle single-day weeks nicely)
        if week["week_start"] == week["week_end"]:
            week_label = f"{week['week_start'].day} {calendar.month_abbr[week['week_start'].month]}"
        else:
            week_label = f"{week['week_start'].day}-{week['week_end'].day} {calendar.month_abbr[week['week_start'].month]}"

        weeks_data.append({
            "week_number": week_idx + 1,
            "week_start": str(week["week_start"]),
            "week_end": str(week["week_end"]),
            "week_label": week_label,
            "employees": list(week_employee_hours.values())
        })

    # Round total hours for each employee
    for emp_id in employee_totals:
        employee_totals[emp_id]["total_hours"] = round(employee_totals[emp_id]["total_hours"], 2)

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "month_start": str(month_start),
        "month_end": str(month_end),
        "weeks": weeks_data,
        "employees": list(employee_totals.values())
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
    Returns total hours for the specified month, with weekly breakdown.
    Weeks run Monday-Sunday.
    Employees can only see their own hours.
    """
    import calendar
    from datetime import timedelta

    # Calculate month start and end dates
    month_start = date_type(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    month_end = date_type(year, month, last_day)

    # Calculate weeks in the month (Mon-Sun)
    weeks = []
    current = month_start
    # Find the Monday of the first week (may be in previous month)
    week_start = current - timedelta(days=current.weekday())

    while week_start <= month_end:
        week_end = week_start + timedelta(days=6)
        # Only include weeks that overlap with this month
        if week_end >= month_start:
            weeks.append({
                "week_start": max(week_start, month_start),
                "week_end": min(week_end, month_end),
            })
        week_start = week_start + timedelta(days=7)

    # Get shifts for the current user only
    shifts = db.query(RosterShift).filter(
        RosterShift.date >= month_start,
        RosterShift.date <= month_end,
        RosterShift.staff_id == current_user.id
    ).all()

    # Calculate total hours
    total_hours = 0.0
    shift_count = 0

    for shift in shifts:
        is_overnight = shift.end_date and shift.end_date != shift.date
        hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
        total_hours += hours
        shift_count += 1

    # Calculate weekly breakdown
    weeks_data = []
    for week_idx, week in enumerate(weeks):
        week_hours = 0.0
        week_shifts = 0

        for shift in shifts:
            if week["week_start"] <= shift.date <= week["week_end"]:
                is_overnight = shift.end_date and shift.end_date != shift.date
                hours = calculate_shift_hours(shift.start_time, shift.end_time, is_overnight)
                week_hours += hours
                week_shifts += 1

        # Format week label (handle single-day weeks nicely)
        if week["week_start"] == week["week_end"]:
            week_label = f"{week['week_start'].day} {calendar.month_abbr[week['week_start'].month]}"
        else:
            week_label = f"{week['week_start'].day}-{week['week_end'].day} {calendar.month_abbr[week['week_start'].month]}"

        weeks_data.append({
            "week_number": week_idx + 1,
            "week_start": str(week["week_start"]),
            "week_end": str(week["week_end"]),
            "week_label": week_label,
            "total_hours": round(week_hours, 2),
            "shift_count": week_shifts
        })

    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "month_start": str(month_start),
        "month_end": str(month_end),
        "employee_id": current_user.id,
        "employee_name": f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email,
        "total_hours": round(total_hours, 2),
        "shift_count": shift_count,
        "weeks": weeks_data
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

        # Check for overlap with existing shifts
        conflicting = check_shift_overlap(
            db, shift_data.staff_id, shift_data.date, start_time, end_time
        )
        if conflicting:
            raise HTTPException(
                status_code=409,
                detail=f"Shift overlaps with existing shift ({format_time(conflicting.start_time)}-{format_time(conflicting.end_time)})"
            )

        # Check if staff is marked unavailable during this shift
        unavail = check_staff_unavailability(
            db, shift_data.staff_id, shift_data.date, start_time, end_time
        )
        if unavail:
            if unavail.start_time and unavail.end_time:
                raise HTTPException(
                    status_code=409,
                    detail=f"Staff is unavailable during this time ({unavail.start_time.strftime('%H:%M')}-{unavail.end_time.strftime('%H:%M')})"
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"Staff is unavailable on {shift_data.date.strftime('%d/%m/%Y')}"
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

    # Handle staff_id: use updates.staff_id_provided to detect if it was explicitly set (even to null)
    if updates.staff_id_provided:
        new_staff_id = updates.staff_id  # Could be None (unassign) or a valid ID
    else:
        new_staff_id = shift.staff_id  # Keep existing

    # Validate staff assignment if changing to a new staff member
    if new_staff_id and new_staff_id != shift.staff_id:
        validate_staff_assignment(db, new_staff_id)

    # Check for overlap if staff, date, or times are changing (only if assigned to someone)
    if new_staff_id:
        conflicting = check_shift_overlap(
            db, new_staff_id, new_date, new_start, new_end, exclude_shift_id=shift_id
        )
        if conflicting:
            raise HTTPException(
                status_code=409,
                detail=f"Shift overlaps with existing shift ({format_time(conflicting.start_time)}-{format_time(conflicting.end_time)})"
            )

        # Check if staff is marked unavailable during this shift
        unavail = check_staff_unavailability(db, new_staff_id, new_date, new_start, new_end)
        if unavail:
            if unavail.start_time and unavail.end_time:
                raise HTTPException(
                    status_code=409,
                    detail=f"Staff is unavailable during this time ({unavail.start_time.strftime('%H:%M')}-{unavail.end_time.strftime('%H:%M')})"
                )
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"Staff is unavailable on {new_date.strftime('%d/%m/%Y')}"
                )

    # Apply updates
    if updates.staff_id_provided:
        shift.staff_id = updates.staff_id  # Can be None to unassign
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
            # Calculate shift time: 2.75 hours before flight departure
            if booking.flight_departure_time:
                flight_mins = booking.flight_departure_time.hour * 60 + booking.flight_departure_time.minute
                shift_start_mins = flight_mins - 165  # 2.75 hours before
                shift_end_mins = flight_mins - 120  # 2 hours before (45 min shift)

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
# Employee Shift Self-Service (Claim/Release)
# ============================================================================

@router.get("/employee/available-shifts", response_model=List[RosterShiftResponse])
async def get_available_shifts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all unassigned shifts from today onwards.
    Returns shifts that are available for employees to claim.
    """
    today = date_type.today()

    # Get all unassigned shifts from today onwards
    shifts = db.query(RosterShift).filter(
        RosterShift.staff_id.is_(None),
        RosterShift.date >= today,
        RosterShift.status != ShiftStatus.CANCELLED
    ).order_by(RosterShift.date, RosterShift.start_time).all()

    return [shift_to_response(shift, db) for shift in shifts]


@router.post("/employee/claim-shift/{shift_id}")
async def claim_shift(
    shift_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Claim an unassigned shift.
    Validates:
    - Shift exists and is unassigned
    - No overlapping shifts for the employee
    - Employee is not on holiday that day
    """
    # Get the shift
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    # Check if shift is already assigned
    if shift.staff_id is not None:
        raise HTTPException(status_code=400, detail="Shift is already assigned to another employee")

    # Check if shift is in the past
    today = date_type.today()
    if shift.date < today:
        raise HTTPException(status_code=400, detail="Cannot claim shifts in the past")

    # Check for overlapping shifts
    conflicting = check_shift_overlap(
        db, current_user.id, shift.date, shift.start_time, shift.end_time
    )
    if conflicting:
        raise HTTPException(
            status_code=409,
            detail=f"You already have a shift at this time ({format_time(conflicting.start_time)}-{format_time(conflicting.end_time)})"
        )

    # Check if employee is on holiday that day
    holiday = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.staff_id == current_user.id,
        EmployeeHoliday.start_date <= shift.date,
        EmployeeHoliday.end_date >= shift.date
    ).first()

    if holiday:
        holiday_type = HOLIDAY_TYPE_CONFIG.get(holiday.holiday_type.value, {}).get('label', 'time off')
        raise HTTPException(
            status_code=409,
            detail=f"You have {holiday_type} booked on this date"
        )

    # Assign the shift to the employee
    shift.staff_id = current_user.id
    db.commit()
    db.refresh(shift)

    return {
        "success": True,
        "message": f"Shift claimed successfully",
        "shift": shift_to_response(shift, db)
    }


# Holiday type config for error messages (matches frontend)
HOLIDAY_TYPE_CONFIG = {
    'holiday': {'label': 'Holiday'},
    'sick': {'label': 'Sick leave'},
    'personal': {'label': 'Personal leave'},
    'other': {'label': 'Time off'},
}


@router.post("/employee/release-shift/{shift_id}")
async def release_shift(
    shift_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Release a shift that the employee has claimed.
    Employees can release shifts with at least 48 hours notice.
    Admin can release any shift (handled by separate admin endpoint).
    """
    # Get the shift
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    # Check if this shift belongs to the employee
    if shift.staff_id != current_user.id:
        raise HTTPException(status_code=403, detail="This shift is not assigned to you")

    # Check 48 hour notice requirement
    now = datetime.utcnow()
    shift_datetime = datetime.combine(shift.date, shift.start_time)
    hours_until_shift = (shift_datetime - now).total_seconds() / 3600

    if hours_until_shift < 48:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot release shift with less than 48 hours notice. Please contact an administrator."
        )

    # Release the shift (set staff_id to None)
    shift.staff_id = None
    db.commit()

    return {
        "success": True,
        "message": "Shift released successfully"
    }


@router.get("/employee/holidays")
async def get_employee_holidays(
    date_from: Optional[date_type] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date_type] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get holidays for the authenticated employee.
    Returns only the logged-in user's holidays (sick days, personal days, etc.).
    """
    query = db.query(EmployeeHoliday).filter(EmployeeHoliday.staff_id == current_user.id)

    # Apply date filters
    if date_from and date_to:
        query = query.filter(
            EmployeeHoliday.start_date <= date_to,
            EmployeeHoliday.end_date >= date_from
        )
    elif date_from:
        query = query.filter(EmployeeHoliday.end_date >= date_from)
    elif date_to:
        query = query.filter(EmployeeHoliday.start_date <= date_to)

    holidays = query.order_by(EmployeeHoliday.start_date).all()

    # Build response with employee details
    result = []
    for holiday in holidays:
        result.append({
            "id": holiday.id,
            "staff_id": holiday.staff_id,
            "staff_first_name": current_user.first_name or "",
            "staff_last_name": current_user.last_name or "",
            "staff_initials": f"{(current_user.first_name or 'X')[0]}{(current_user.last_name or 'X')[0]}".upper(),
            "start_date": str(holiday.start_date),
            "end_date": str(holiday.end_date),
            "start_time": holiday.start_time.strftime("%H:%M") if holiday.start_time else None,
            "end_time": holiday.end_time.strftime("%H:%M") if holiday.end_time else None,
            "holiday_type": holiday.holiday_type.value,
            "notes": holiday.notes,
            "created_at": holiday.created_at.isoformat() if holiday.created_at else None,
        })

    return result


# ============================================================================
# Employee Unavailability Self-Service
# ============================================================================

def parse_time_for_unavailability(time_str: Optional[str]) -> Optional[time]:
    """Parse time string (HH:MM) to time object for unavailability."""
    if not time_str:
        return None
    try:
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def check_shift_conflict_for_unavailability(
    db: Session,
    staff_id: int,
    start_date: date_type,
    end_date: date_type,
    start_time: Optional[time],
    end_time: Optional[time]
) -> Optional[RosterShift]:
    """
    Check if the employee has any shifts during the unavailability period.
    Returns the conflicting shift if found, None otherwise.
    """
    # Get all shifts in the date range
    shifts = db.query(RosterShift).filter(
        RosterShift.staff_id == staff_id,
        RosterShift.date >= start_date,
        RosterShift.date <= end_date
    ).all()

    if not shifts:
        return None

    # If no times specified (full day unavailability), any shift conflicts
    if start_time is None and end_time is None:
        return shifts[0] if shifts else None

    # Check for time overlaps
    for shift in shifts:
        shift_start = shift.start_time
        shift_end = shift.end_time

        # For partial day unavailability, check time overlap
        unavail_start = start_time or time(0, 0)
        unavail_end = end_time or time(23, 59)

        # Check if shift overlaps with unavailability period
        # Overlap occurs if shift doesn't end before unavailability starts
        # AND shift doesn't start after unavailability ends
        if not (shift_end <= unavail_start or shift_start >= unavail_end):
            return shift

    return None


@router.post("/employee/unavailability")
async def add_employee_unavailability(
    start_date: str = Query(..., description="Start date (DD/MM/YYYY)"),
    end_date: str = Query(..., description="End date (DD/MM/YYYY)"),
    start_time: Optional[str] = Query(None, description="Start time (HH:MM) for partial day, or omit for full day"),
    end_time: Optional[str] = Query(None, description="End time (HH:MM) for partial day, or omit for full day"),
    notes: Optional[str] = Query(None, description="Optional notes"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Employee self-service: Mark yourself as unavailable.

    - Employees can only add unavailability for themselves
    - Cannot add unavailability if there's a conflicting shift (must release shift first)
    - Supports full days or partial days with times (UK timezone)
    - Dates in DD/MM/YYYY format, times in HH:MM 24-hour format
    """
    # Parse dates (DD/MM/YYYY format as per spec)
    try:
        start_parts = start_date.split("/")
        parsed_start_date = date_type(int(start_parts[2]), int(start_parts[1]), int(start_parts[0]))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid start_date format. Use DD/MM/YYYY")

    try:
        end_parts = end_date.split("/")
        parsed_end_date = date_type(int(end_parts[2]), int(end_parts[1]), int(end_parts[0]))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid end_date format. Use DD/MM/YYYY")

    # Validate date range
    if parsed_end_date < parsed_start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")

    # Parse times
    parsed_start_time = parse_time_for_unavailability(start_time)
    parsed_end_time = parse_time_for_unavailability(end_time)

    # Validate time range if both provided
    if parsed_start_time and parsed_end_time and parsed_end_time <= parsed_start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    # Check for conflicting shifts
    conflicting_shift = check_shift_conflict_for_unavailability(
        db, current_user.id, parsed_start_date, parsed_end_date,
        parsed_start_time, parsed_end_time
    )

    if conflicting_shift:
        shift_date = conflicting_shift.date.strftime("%d/%m/%Y")
        shift_time = f"{conflicting_shift.start_time.strftime('%H:%M')}-{conflicting_shift.end_time.strftime('%H:%M')}"
        raise HTTPException(
            status_code=409,
            detail=f"You have a shift on {shift_date} ({shift_time}). Please release the shift first before marking yourself unavailable."
        )

    # Create the unavailability record
    unavailability = EmployeeHoliday(
        staff_id=current_user.id,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
        start_time=parsed_start_time,
        end_time=parsed_end_time,
        holiday_type=HolidayType.UNAVAILABLE,
        notes=notes,
        created_by=current_user.email
    )

    db.add(unavailability)
    db.commit()
    db.refresh(unavailability)

    return {
        "success": True,
        "message": "Unavailability added successfully",
        "unavailability": {
            "id": unavailability.id,
            "start_date": unavailability.start_date.strftime("%d/%m/%Y"),
            "end_date": unavailability.end_date.strftime("%d/%m/%Y"),
            "start_time": unavailability.start_time.strftime("%H:%M") if unavailability.start_time else None,
            "end_time": unavailability.end_time.strftime("%H:%M") if unavailability.end_time else None,
            "notes": unavailability.notes
        }
    }


@router.get("/employee/unavailability")
async def get_employee_unavailability(
    date_from: Optional[str] = Query(None, description="Filter from date (DD/MM/YYYY)"),
    date_to: Optional[str] = Query(None, description="Filter to date (DD/MM/YYYY)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the authenticated employee's unavailability records.
    Only returns records with holiday_type = 'unavailable'.
    """
    query = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.staff_id == current_user.id,
        EmployeeHoliday.holiday_type == HolidayType.UNAVAILABLE
    )

    # Parse and apply date filters
    if date_from:
        try:
            parts = date_from.split("/")
            parsed_from = date_type(int(parts[2]), int(parts[1]), int(parts[0]))
            query = query.filter(EmployeeHoliday.end_date >= parsed_from)
        except (ValueError, IndexError):
            pass  # Ignore invalid date filter

    if date_to:
        try:
            parts = date_to.split("/")
            parsed_to = date_type(int(parts[2]), int(parts[1]), int(parts[0]))
            query = query.filter(EmployeeHoliday.start_date <= parsed_to)
        except (ValueError, IndexError):
            pass  # Ignore invalid date filter

    unavailabilities = query.order_by(EmployeeHoliday.start_date).all()

    result = []
    for u in unavailabilities:
        result.append({
            "id": u.id,
            "start_date": u.start_date.strftime("%d/%m/%Y"),
            "end_date": u.end_date.strftime("%d/%m/%Y"),
            "start_time": u.start_time.strftime("%H:%M") if u.start_time else None,
            "end_time": u.end_time.strftime("%H:%M") if u.end_time else None,
            "notes": u.notes,
            "created_at": u.created_at.isoformat() if u.created_at else None
        })

    return result


@router.delete("/employee/unavailability/{unavailability_id}")
async def delete_employee_unavailability(
    unavailability_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an unavailability record.
    Employees can only delete their own unavailability records.
    """
    unavailability = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.id == unavailability_id,
        EmployeeHoliday.staff_id == current_user.id,
        EmployeeHoliday.holiday_type == HolidayType.UNAVAILABLE
    ).first()

    if not unavailability:
        raise HTTPException(status_code=404, detail="Unavailability record not found")

    db.delete(unavailability)
    db.commit()

    return {
        "success": True,
        "message": "Unavailability deleted successfully"
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


# ============================================================================
# Employee Holidays Endpoints (Admin Only)
# ============================================================================

def holiday_to_response(holiday: EmployeeHoliday) -> dict:
    """Convert EmployeeHoliday model to response dict."""
    return {
        "id": holiday.id,
        "staff_id": holiday.staff_id,
        "staff_first_name": holiday.staff.first_name if holiday.staff else None,
        "staff_last_name": holiday.staff.last_name if holiday.staff else None,
        "staff_initials": holiday.staff_initials,
        "start_date": str(holiday.start_date),
        "end_date": str(holiday.end_date),
        "start_time": holiday.start_time.strftime("%H:%M") if holiday.start_time else None,
        "end_time": holiday.end_time.strftime("%H:%M") if holiday.end_time else None,
        "holiday_type": holiday.holiday_type.value,
        "notes": holiday.notes,
        "created_at": holiday.created_at.isoformat() if holiday.created_at else None,
    }


@router.get("/holidays")
async def list_holidays(
    date_from: Optional[date_type] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date_type] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    staff_id: Optional[int] = Query(None, description="Filter by staff member"),
    db: Session = Depends(get_db)
):
    """
    List employee holidays with optional filters.
    Returns holidays that overlap with the given date range.
    """
    query = db.query(EmployeeHoliday)

    if date_from and date_to:
        # Find holidays that overlap with the date range
        query = query.filter(
            and_(
                EmployeeHoliday.start_date <= date_to,
                EmployeeHoliday.end_date >= date_from
            )
        )
    elif date_from:
        query = query.filter(EmployeeHoliday.end_date >= date_from)
    elif date_to:
        query = query.filter(EmployeeHoliday.start_date <= date_to)

    if staff_id:
        query = query.filter(EmployeeHoliday.staff_id == staff_id)

    holidays = query.order_by(EmployeeHoliday.start_date).all()

    return [holiday_to_response(h) for h in holidays]


@router.get("/holidays/for-date")
async def get_holidays_for_date(
    date: date_type = Query(..., description="Date to check (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Get all employees on holiday for a specific date.
    Returns list of staff IDs and their holiday info.
    """
    holidays = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.start_date <= date,
        EmployeeHoliday.end_date >= date
    ).all()

    return [holiday_to_response(h) for h in holidays]


@router.get("/holidays/{holiday_id}")
async def get_holiday(
    holiday_id: int,
    db: Session = Depends(get_db)
):
    """Get a single holiday by ID."""
    holiday = db.query(EmployeeHoliday).filter(EmployeeHoliday.id == holiday_id).first()

    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    return holiday_to_response(holiday)


@router.post("/holidays", status_code=201)
async def create_holiday(
    staff_id: int,
    start_date: date_type,
    end_date: date_type,
    background_tasks: BackgroundTasks,
    holiday_type: str = "holiday",
    notes: Optional[str] = None,
    start_time: Optional[str] = Query(None, description="Start time in HH:MM format (for partial day unavailability)"),
    end_time: Optional[str] = Query(None, description="End time in HH:MM format (for partial day unavailability)"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new employee holiday/time-off record.
    For partial-day unavailability, include start_time and end_time in HH:MM format.
    """
    # Validate staff exists
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    # Validate dates
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    # Validate holiday type
    try:
        h_type = HolidayType(holiday_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid holiday type. Must be one of: {[t.value for t in HolidayType]}"
        )

    # Parse times first (needed for overlap check)
    parsed_start_time = None
    parsed_end_time = None
    if start_time:
        parsed_start_time = parse_time_for_unavailability(start_time)
        if parsed_start_time is None:
            raise HTTPException(status_code=400, detail="Invalid start_time format. Use HH:MM")
    if end_time:
        parsed_end_time = parse_time_for_unavailability(end_time)
        if parsed_end_time is None:
            raise HTTPException(status_code=400, detail="Invalid end_time format. Use HH:MM")

    # Check for overlapping holidays (considering time ranges)
    # Get all entries with overlapping dates first
    overlapping_dates = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.staff_id == staff_id,
        EmployeeHoliday.start_date <= end_date,
        EmployeeHoliday.end_date >= start_date
    ).all()

    # Check each one for actual time overlap
    for existing in overlapping_dates:
        if check_holiday_time_overlap(
            existing.start_time, existing.end_time,
            parsed_start_time, parsed_end_time
        ):
            # Format the error message with time info if applicable
            time_info = ""
            if existing.start_time and existing.end_time:
                time_info = f" {format_time(existing.start_time)}-{format_time(existing.end_time)}"
            raise HTTPException(
                status_code=409,
                detail=f"Holiday overlaps with existing entry ({existing.start_date} to {existing.end_date}{time_info})"
            )

    # Check for existing shifts during the holiday period
    conflicting_shifts = db.query(RosterShift).filter(
        RosterShift.staff_id == staff_id,
        RosterShift.date >= start_date,
        RosterShift.date <= end_date,
        RosterShift.status != ShiftStatus.CANCELLED
    ).all()

    if conflicting_shifts:
        shift_dates = sorted(set(str(s.date) for s in conflicting_shifts))
        if len(shift_dates) == 1:
            raise HTTPException(
                status_code=409,
                detail=f"Staff member has a shift scheduled on {shift_dates[0]}. Please remove the shift first."
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Staff member has {len(conflicting_shifts)} shifts scheduled during this period ({shift_dates[0]} to {shift_dates[-1]}). Please remove the shifts first."
            )

    new_holiday = EmployeeHoliday(
        staff_id=staff_id,
        start_date=start_date,
        end_date=end_date,
        start_time=parsed_start_time,
        end_time=parsed_end_time,
        holiday_type=h_type,
        notes=notes,
        created_by=current_user.email
    )

    db.add(new_holiday)
    db.commit()
    db.refresh(new_holiday)

    # Roster planner shadow mode: a new holiday changes which staff are
    # eligible across the rolling window. Re-evaluate.
    background_tasks.add_task(
        fire_engine_async, TRIGGER_HOLIDAY_CHANGED, str(new_holiday.id)
    )

    return holiday_to_response(new_holiday)


@router.put("/holidays/{holiday_id}")
async def update_holiday(
    holiday_id: int,
    background_tasks: BackgroundTasks,
    start_date: Optional[date_type] = None,
    end_date: Optional[date_type] = None,
    holiday_type: Optional[str] = None,
    notes: Optional[str] = None,
    start_time: Optional[str] = Query(None, description="Start time in HH:MM format (for partial day unavailability)"),
    end_time: Optional[str] = Query(None, description="End time in HH:MM format (for partial day unavailability)"),
    clear_times: bool = Query(False, description="Set to true to clear start_time/end_time (make full day)"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update an existing holiday/unavailability record."""
    holiday = db.query(EmployeeHoliday).filter(EmployeeHoliday.id == holiday_id).first()

    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    # Apply updates
    if start_date is not None:
        holiday.start_date = start_date
    if end_date is not None:
        holiday.end_date = end_date
    if holiday_type is not None:
        try:
            holiday.holiday_type = HolidayType(holiday_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid holiday type. Must be one of: {[t.value for t in HolidayType]}"
            )
    if notes is not None:
        holiday.notes = notes

    # Handle time updates for partial-day unavailability
    if clear_times:
        holiday.start_time = None
        holiday.end_time = None
    else:
        if start_time is not None:
            parsed_start = parse_time_for_unavailability(start_time)
            if parsed_start is None:
                raise HTTPException(status_code=400, detail="Invalid start_time format. Use HH:MM")
            holiday.start_time = parsed_start
        if end_time is not None:
            parsed_end = parse_time_for_unavailability(end_time)
            if parsed_end is None:
                raise HTTPException(status_code=400, detail="Invalid end_time format. Use HH:MM")
            holiday.end_time = parsed_end

    # Validate dates after updates
    if holiday.end_date < holiday.start_date:
        raise HTTPException(status_code=400, detail="End date must be on or after start date")

    # Check for overlapping holidays (excluding self, considering time ranges)
    overlapping_dates = db.query(EmployeeHoliday).filter(
        EmployeeHoliday.staff_id == holiday.staff_id,
        EmployeeHoliday.id != holiday_id,
        EmployeeHoliday.start_date <= holiday.end_date,
        EmployeeHoliday.end_date >= holiday.start_date
    ).all()

    # Check each one for actual time overlap
    for existing in overlapping_dates:
        if check_holiday_time_overlap(
            existing.start_time, existing.end_time,
            holiday.start_time, holiday.end_time
        ):
            # Format the error message with time info if applicable
            time_info = ""
            if existing.start_time and existing.end_time:
                time_info = f" {format_time(existing.start_time)}-{format_time(existing.end_time)}"
            raise HTTPException(
                status_code=409,
                detail=f"Holiday overlaps with existing entry ({existing.start_date} to {existing.end_date}{time_info})"
            )

    # Check for existing shifts during the updated holiday period
    conflicting_shifts = db.query(RosterShift).filter(
        RosterShift.staff_id == holiday.staff_id,
        RosterShift.date >= holiday.start_date,
        RosterShift.date <= holiday.end_date,
        RosterShift.status != ShiftStatus.CANCELLED
    ).all()

    if conflicting_shifts:
        shift_dates = sorted(set(str(s.date) for s in conflicting_shifts))
        if len(shift_dates) == 1:
            raise HTTPException(
                status_code=409,
                detail=f"Staff member has a shift scheduled on {shift_dates[0]}. Please remove the shift first."
            )
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Staff member has {len(conflicting_shifts)} shifts scheduled during this period ({shift_dates[0]} to {shift_dates[-1]}). Please remove the shifts first."
            )

    db.commit()
    db.refresh(holiday)

    # Roster planner shadow mode: a changed holiday can shift staff
    # eligibility across the rolling window. Re-evaluate.
    background_tasks.add_task(
        fire_engine_async, TRIGGER_HOLIDAY_CHANGED, str(holiday.id)
    )

    return holiday_to_response(holiday)


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(
    holiday_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a holiday (hard delete)."""
    holiday = db.query(EmployeeHoliday).filter(EmployeeHoliday.id == holiday_id).first()

    if not holiday:
        raise HTTPException(status_code=404, detail="Holiday not found")

    holiday_id_for_audit = str(holiday.id)
    db.delete(holiday)
    db.commit()

    # Roster planner shadow mode: a deleted holiday returns staff to the
    # eligible pool across the rolling window. Re-evaluate.
    background_tasks.add_task(
        fire_engine_async, TRIGGER_HOLIDAY_CHANGED, holiday_id_for_audit
    )

    return {"success": True, "message": "Holiday deleted"}


# ============================================================================
# QA Roster Planner (Phase 1) — read-only preview + settings
# Rules locked 2026-04-24. See backend/docs/SPEC.md § Roster Planner.
# Gated by user_id IN QA_USER_IDS as defence-in-depth (UI also hides the tab).
# No writes to roster_shifts occur in Phase 1.
# ============================================================================

QA_USER_IDS = {1, 2}

_PLANNER_DEFAULT_SETTINGS = {
    "window_days": 28,
    "gap_max_minutes": 120,
    "mixed_gap_max_minutes": 150,
    "buffer_minutes": 30,
    "staffing_thresholds": [
        {"max_peak": 3, "staff": 1},
        {"max_peak": 999, "staff": 2},
    ],
    "max_hours_per_week": 40,
    "min_rest_hours": 8,
    "untouchable_hours": 24,
    "preview_enabled": True,
    "commit_enabled": False,
}


async def require_qa_admin(current_user: User = Depends(require_admin)) -> User:
    if current_user.id not in QA_USER_IDS:
        raise HTTPException(status_code=403, detail="QA access required")
    return current_user


def _load_planner_settings_rows(db: Session) -> dict:
    rows = db.query(DbRosterPlannerSettings).all()
    parsed: dict = {}
    for row in rows:
        try:
            parsed[row.key] = json.loads(row.value_json)
        except (json.JSONDecodeError, TypeError):
            continue
    return parsed


def _settings_response(parsed: dict) -> RosterPlannerSettingsResponse:
    merged = {**_PLANNER_DEFAULT_SETTINGS, **parsed}
    return RosterPlannerSettingsResponse(**merged)


@router.get(
    "/admin/qa/roster-planner/settings",
    response_model=RosterPlannerSettingsResponse,
)
async def get_roster_planner_settings(
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    return _settings_response(_load_planner_settings_rows(db))


@router.patch(
    "/admin/qa/roster-planner/settings",
    response_model=RosterPlannerSettingsResponse,
)
async def patch_roster_planner_settings(
    payload: RosterPlannerSettingsUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    # exclude_unset guards against clobbering fields the admin didn't touch
    # (2026-04-06 shift-unassign lesson).
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        row = (
            db.query(DbRosterPlannerSettings)
            .filter(DbRosterPlannerSettings.key == key)
            .one_or_none()
        )
        value_json = json.dumps(value)
        if row is None:
            db.add(
                DbRosterPlannerSettings(
                    key=key, value_json=value_json, updated_by=current_user.id
                )
            )
        else:
            row.value_json = value_json
            row.updated_by = current_user.id
            row.updated_at = datetime.utcnow()
    if changes:
        db.commit()
        # Roster planner shadow mode: rule changes (gap, caps, thresholds)
        # change engine output for the same input data. Re-evaluate.
        background_tasks.add_task(
            fire_engine_async,
            TRIGGER_SETTINGS_CHANGED,
            ",".join(sorted(changes.keys())),
        )
    return _settings_response(_load_planner_settings_rows(db))


@router.post(
    "/admin/qa/roster-planner/propose",
    response_model=RosterProposalResponse,
)
async def propose_roster_endpoint(
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    started_at = datetime.utcnow()
    parsed = _load_planner_settings_rows(db)
    settings_snapshot = _settings_response(parsed)
    engine_settings = PlannerSettings.from_kv(parsed)
    now = datetime.now(UK_TZ)
    window_start = now.date()
    window_end = window_start + timedelta(days=engine_settings.window_days)

    bookings = (
        db.query(Booking)
        .filter(
            Booking.status == BookingStatus.CONFIRMED,
            or_(
                and_(
                    Booking.dropoff_date >= window_start,
                    Booking.dropoff_date < window_end,
                ),
                and_(
                    Booking.pickup_date >= window_start,
                    Booking.pickup_date < window_end,
                ),
            ),
        )
        .all()
    )
    shifts = (
        db.query(RosterShift)
        .filter(
            RosterShift.date >= window_start,
            RosterShift.date < window_end,
        )
        .all()
    )
    staff = (
        db.query(User)
        .filter(User.is_active == True, User.is_admin == False)
        .all()
    )
    holidays = (
        db.query(EmployeeHoliday)
        .filter(
            EmployeeHoliday.start_date < window_end,
            EmployeeHoliday.end_date >= window_start,
        )
        .all()
    )

    result = propose_roster(
        bookings=bookings,
        shifts=shifts,
        staff=staff,
        holidays=holidays,
        settings=engine_settings,
        now=now,
    )
    result["settings_snapshot"] = settings_snapshot.model_dump()

    # Shadow mode: every /propose run leaves an audit row. Failure is
    # swallowed by record_run so the response still reaches the caller.
    record_run(
        db,
        trigger_event=TRIGGER_MANUAL,
        trigger_ref=None,
        proposal=result,
        started_at=started_at,
    )
    return result


# =====================================================================================
# Shadow-mode run history — the QA tab's history strip and detail view
# =====================================================================================


@router.get(
    "/admin/qa/roster-planner/runs",
    response_model=List[PlannerRunListItem],
)
async def list_planner_runs(
    limit: int = Query(50, ge=1, le=200),
    trigger_event: Optional[str] = Query(None, description="Filter by trigger_event (e.g. booking_confirmed)"),
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """List recent shadow-mode engine runs, newest first.

    Each row is the slim summary the QA history strip needs (timestamp,
    trigger, window, duration). Full proposal lives at /runs/{run_id}.
    """
    from db_models import PlannerRun

    q = db.query(PlannerRun)
    if trigger_event:
        q = q.filter(PlannerRun.trigger_event == trigger_event)
    rows = q.order_by(PlannerRun.triggered_at.desc()).limit(limit).all()

    out = []
    for r in rows:
        # Pull summary out of proposal_json so the strip can show volume
        # at a glance without loading the full proposal.
        summary = None
        if r.proposal_json:
            try:
                summary = json.loads(r.proposal_json).get("summary")
            except (TypeError, ValueError):
                summary = None
        out.append(
            PlannerRunListItem(
                run_id=r.run_id,
                triggered_at=r.triggered_at,
                trigger_event=r.trigger_event,
                trigger_ref=r.trigger_ref,
                window_start=r.window_start,
                window_end=r.window_end,
                duration_ms=r.duration_ms,
                has_error=bool(r.error_text),
                summary=summary,
            )
        )
    return out


@router.get(
    "/admin/qa/roster-planner/runs/{run_id}",
    response_model=PlannerRunDetail,
)
async def get_planner_run(
    run_id: str,
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Full proposal for one run — feeds the calendar render in the QA tab."""
    from db_models import PlannerRun

    row = (
        db.query(PlannerRun)
        .filter(PlannerRun.run_id == run_id)
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="planner run not found")

    proposal = None
    if row.proposal_json:
        try:
            proposal = json.loads(row.proposal_json)
        except (TypeError, ValueError):
            proposal = None
    diff = None
    if row.diff_vs_current_json:
        try:
            diff = json.loads(row.diff_vs_current_json)
        except (TypeError, ValueError):
            diff = None
    warnings = []
    if row.warnings_json:
        try:
            warnings = json.loads(row.warnings_json)
        except (TypeError, ValueError):
            warnings = []

    return PlannerRunDetail(
        run_id=row.run_id,
        triggered_at=row.triggered_at,
        trigger_event=row.trigger_event,
        trigger_ref=row.trigger_ref,
        window_start=row.window_start,
        window_end=row.window_end,
        proposal=proposal,
        diff_vs_current=diff,
        warnings=warnings,
        duration_ms=row.duration_ms,
        error_text=row.error_text,
    )


# =====================================================================================
# Shadow-mode QA feedback — per-engine-decision review notes
# =====================================================================================


@router.post(
    "/admin/qa/roster-planner/runs/{run_id}/feedback",
    response_model=PlannerRunFeedbackResponse,
    status_code=201,
)
async def submit_planner_run_feedback(
    run_id: str,
    payload: PlannerRunFeedbackCreate,
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Capture QA's verdict on one engine assignment decision.

    Tied to a specific (run_id, shift fingerprint). The shift fingerprint
    is denormalised onto the row so feedback survives if the parent run
    is later pruned, and so cross-run pattern queries work.
    """
    from db_models import PlannerRun, PlannerRunFeedback

    parent = (
        db.query(PlannerRun).filter(PlannerRun.run_id == run_id).one_or_none()
    )
    if not parent:
        raise HTTPException(status_code=404, detail="planner run not found")

    row = PlannerRunFeedback(
        run_id=run_id,
        shift_date=payload.shift_date,
        shift_start_time=payload.shift_start_time,
        shift_end_time=payload.shift_end_time,
        shift_staff_id=payload.shift_staff_id,
        proposed_shift_index=payload.proposed_shift_index,
        severity=payload.severity,
        comment=payload.comment,
        submitted_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/admin/qa/roster-planner/feedback",
    response_model=List[PlannerRunFeedbackResponse],
)
async def list_planner_run_feedback(
    shift_date: Optional[date_type] = Query(None),
    shift_staff_id: Optional[int] = Query(None),
    shift_start_time: Optional[str] = Query(
        None, description="HH:MM — used with shift_staff_id for cross-run pattern queries"
    ),
    run_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Retrieve feedback rows. Common access patterns:

    - `?shift_date=YYYY-MM-DD` — all feedback on shifts on this date,
      across runs (the modal's "prior feedback for this date" panel).
    - `?shift_staff_id=N&shift_start_time=HH:MM` — pattern detection
      ("this staff on this shift type keeps getting flagged").
    - `?run_id=X` — all feedback recorded against one specific run.
    """
    from db_models import PlannerRunFeedback

    q = db.query(PlannerRunFeedback)
    if shift_date is not None:
        q = q.filter(PlannerRunFeedback.shift_date == shift_date)
    if shift_staff_id is not None:
        q = q.filter(PlannerRunFeedback.shift_staff_id == shift_staff_id)
    if shift_start_time:
        try:
            parsed = time.fromisoformat(shift_start_time)
        except ValueError:
            raise HTTPException(status_code=422, detail="shift_start_time must be HH:MM")
        q = q.filter(PlannerRunFeedback.shift_start_time == parsed)
    if run_id:
        q = q.filter(PlannerRunFeedback.run_id == run_id)
    return q.order_by(PlannerRunFeedback.submitted_at.desc()).limit(limit).all()
