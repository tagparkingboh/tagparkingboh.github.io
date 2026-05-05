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
from db_models import User, Booking, RosterShift, ShiftType, ShiftStatus, Session as DbSession, BookingStatus, ShiftBookingLink, EmployeeHoliday, HolidayType, RosterPlannerSettings as DbRosterPlannerSettings, AuditLog, AuditLogEvent
from models import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    RosterShiftCreate, RosterShiftUpdate, RosterShiftResponse,
    RosterShiftDuplicateRequest, RosterShiftMergeRequest, RosterShiftSplitRequest,
    AutoAssignRequest, AutoAssignResponse, OperationalWarning,
    ShiftTypeEnum, ShiftStatusEnum, LinkedBookingInfo,
    RosterPlannerSettingsResponse, RosterPlannerSettingsUpdate,
    RosterProposalResponse,
    PlannerRunListItem, PlannerRunDetail,
    PlannerRunFeedbackCreate, PlannerRunFeedbackResponse, PlannerRunFeedbackOverride,
    PlannerCommitRequest, PlannerCommitResponse, PlannerUndoResponse,
    CommittedShiftSnapshot,
    TeamShiftResponse,
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
    parts = (time_str or "").split(":")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {time_str!r} (expected HH:MM)")
    try:
        return time(int(parts[0]), int(parts[1]))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {time_str!r} (expected HH:MM)")


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


def normalise_uk_phone(phone: Optional[str]) -> Optional[str]:
    """Normalise a UK phone number to E.164 (+44...) for display + tel: links.

    Handles the common storage variations across the users table:
      '07911123456' → '+447911123456'
      '+447911123456' → '+447911123456'
      '447911123456' → '+447911123456'
      '07911 123 456' → '+447911123456' (spaces stripped)
    Empty / None / unrecognisable input → None.
    """
    if not phone:
        return None
    digits_only = "".join(c for c in phone if c.isdigit() or c == "+")
    if not digits_only or digits_only == "+":
        return None
    if digits_only.startswith("+"):
        return digits_only
    if digits_only.startswith("44"):
        return "+" + digits_only
    if digits_only.startswith("0"):
        return "+44" + digits_only[1:]
    # Unrecognised — surface as-is so it's visible rather than silently dropped.
    return digits_only


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
        intended_driver_type=(
            shift.intended_driver_type
            if isinstance(getattr(shift, "intended_driver_type", None), str)
            else "jockey"
        ),
        created_source=(
            shift.created_source
            if isinstance(getattr(shift, "created_source", None), str)
            else None
        ),
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
    auto_assign_excluded: Optional[bool] = Query(
        None,
        description="Filter by auto_assign_excluded status. Pass false to get the assignable pool (excluded users hidden — used by the QA Roster Planner edit modal).",
    ),
    db: Session = Depends(get_db)
):
    """
    List ALL users (both admins and employees) for shift assignment.
    Optionally filter by is_active and/or auto_assign_excluded status.
    """
    query = db.query(User)

    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if auto_assign_excluded is not None:
        query = query.filter(User.auto_assign_excluded == auto_assign_excluded)

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
    source: Optional[str] = Query(
        None,
        description=(
            "Filter by created_source. Pass 'auto' to limit to auto-created shifts "
            "(used by the new self-contained Roster Planner Calendar). Default "
            "excludes 'auto' shifts so the regular admin Calendar stays clean."
        ),
    ),
    db: Session = Depends(get_db)
):
    """
    List roster shifts with optional filters.
    - date: Filter by specific date
    - date_from/date_to: Filter by date range
    - staff_id: Filter by staff member
    - week_start: Filter by week (Mon-Sun starting from this date)
    - source: 'auto' to scope to auto-created shifts; default excludes them
    """
    query = db.query(RosterShift)

    # Sever auto-shifts from the regular admin Roster Calendar by default.
    # The new Calendar embedded on the Planner page passes source='auto' to
    # opt in. 'all' bypasses the default exclusion so the v3 admin toggle can
    # show every shift regardless of source. Other named sources ('manual',
    # 'planner') filter exactly.
    if source == "all":
        pass  # no filter
    elif source == "auto":
        query = query.filter(RosterShift.created_source == "auto")
    elif source in ("manual", "planner"):
        query = query.filter(RosterShift.created_source == source)
    else:
        query = query.filter(RosterShift.created_source != "auto")

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
    source: Optional[str] = Query(
        None,
        description=(
            "Same semantics as /roster/monthly-hours: 'auto' includes "
            "unassigned auto-shifts under a virtual 'Unassigned' bucket; "
            "default excludes auto and requires an assigned staff_id."
        ),
    ),
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
    )

    if source == "all":
        query = query.filter(RosterShift.staff_id.isnot(None))
    elif source == "auto":
        query = query.filter(RosterShift.created_source == "auto")
    elif source in ("manual", "planner"):
        query = query.filter(
            RosterShift.created_source == source,
            RosterShift.staff_id.isnot(None),
        )
    else:
        query = query.filter(
            RosterShift.created_source != "auto",
            RosterShift.staff_id.isnot(None),
        )

    if staff_id:
        query = query.filter(RosterShift.staff_id == staff_id)

    shifts = query.all()

    # Group shifts by employee and calculate hours
    employee_hours = {}
    for shift in shifts:
        if shift.staff_id not in employee_hours:
            if shift.staff_id is None:
                employee_hours[None] = {
                    "employee_id": None,
                    "employee_name": "Unassigned",
                    "total_hours": 0.0,
                    "shift_count": 0,
                    "daily_hours": {str(week_start + timedelta(days=i)): 0.0 for i in range(7)},
                }
            else:
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
    source: Optional[str] = Query(
        None,
        description=(
            "Filter by created_source. Pass 'auto' to scope to auto-roster "
            "shifts (unassigned shifts are included and bucketed under a "
            "virtual 'Unassigned' employee). Default excludes 'auto' shifts "
            "and requires staff_id NOT NULL — same as the regular admin "
            "Calendar's payroll view."
        ),
    ),
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
    )

    # Source filter — keeps the regular admin payroll view exclusive of
    # auto-roster shifts, while opting in via `?source=auto` includes
    # unassigned auto-shifts (bucketed under a virtual 'Unassigned' row).
    # `?source=all` shows everything (v3 admin toggle).
    if source == "all":
        query = query.filter(RosterShift.staff_id.isnot(None))
    elif source == "auto":
        query = query.filter(RosterShift.created_source == "auto")
    elif source in ("manual", "planner"):
        query = query.filter(
            RosterShift.created_source == source,
            RosterShift.staff_id.isnot(None),
        )
    else:
        query = query.filter(
            RosterShift.created_source != "auto",
            RosterShift.staff_id.isnot(None),
        )

    if staff_id:
        query = query.filter(RosterShift.staff_id == staff_id)

    shifts = query.all()

    # Build employee info cache. Auto-roster mode includes unassigned shifts;
    # those bucket under `staff_id=None` with a virtual 'Unassigned' label.
    employee_info = {}
    for shift in shifts:
        if shift.staff_id in employee_info:
            continue
        if shift.staff_id is None:
            employee_info[None] = {
                "employee_id": None,
                "employee_name": "Unassigned",
            }
            continue
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

    # If staff is assigned, intended_driver_type follows that user's
    # driver_type — the assigned user is the source of truth. Only when
    # staff_id is None does the request's intended_driver_type matter.
    intended = shift_data.intended_driver_type or "jockey"
    if shift_data.staff_id:
        assigned = db.query(User).filter(User.id == shift_data.staff_id).first()
        if assigned and getattr(assigned, "driver_type", None) in ("jockey", "fleet"):
            intended = assigned.driver_type

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
        notes=shift_data.notes,
        intended_driver_type=intended,
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
    # If staff is now assigned, intended_driver_type follows the assigned
    # user's driver_type (source of truth). Otherwise honour the request.
    if updates.staff_id_provided and updates.staff_id:
        assigned = db.query(User).filter(User.id == updates.staff_id).first()
        if assigned and getattr(assigned, "driver_type", None) in ("jockey", "fleet"):
            shift.intended_driver_type = assigned.driver_type
    elif updates.intended_driver_type is not None:
        shift.intended_driver_type = updates.intended_driver_type

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
# Per-Shift Action Endpoints (Roster Planner v3 Phase 2 — locked 2026-05-04)
#
# These endpoints back the per-shift action bar in the day-detail modal.
# All four are admin-only, all four operate on a single roster_shifts row,
# and all four are intentionally narrow — bulk operations are loop-on-the-
# frontend (see SPEC.md v3 Phase 3) so audit stays one-row-per-action.
# ============================================================================


def _shift_window_dt(shift: RosterShift) -> tuple[datetime, datetime]:
    """Naive [start, end] datetime for a shift, expanding overnight via end_date."""
    end_date = shift.end_date or shift.date
    start_dt = datetime.combine(shift.date, shift.start_time)
    end_dt = datetime.combine(end_date, shift.end_time)
    # Defensive: if end_date wasn't set but end_time wraps past midnight, treat as next day.
    if end_dt <= start_dt:
        end_dt = end_dt + timedelta(days=1)
    return start_dt, end_dt


@router.post("/roster/{shift_id}/duplicate", response_model=List[RosterShiftResponse])
async def duplicate_shift(
    shift_id: int,
    body: RosterShiftDuplicateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Duplicate a roster shift.

    Modes (mutually exclusive — both set returns 422 per the deferred Phase 4 rule):
    - `target_date` only → 1 copy on that date, same staff/time. Linked
      bookings re-attach if their event_time falls inside the copy's window
      (uses the v3 flight-arrival back-date heuristic via _events_for_booking).
    - `staff_ids` and/or `add_unassigned_jockey` / `add_unassigned_fleet` → N
      copies on the source's date, one per target.

    Date-copy result is always `created_source='manual'` regardless of the
    source's source — admin took an explicit action so lifecycle ownership
    transfers off the auto-roster (per SPEC.md v3).
    """
    source = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Shift not found")

    has_date = body.target_date is not None
    has_staff = bool(body.staff_ids) or body.add_unassigned_jockey or body.add_unassigned_fleet

    if has_date and has_staff:
        raise HTTPException(
            status_code=422,
            detail="Bulk staff-add (target_date + staff_ids) is deferred. Pick one mode per request.",
        )
    if not has_date and not has_staff:
        raise HTTPException(
            status_code=422,
            detail="Specify either target_date or staff_ids (or unassigned flags) to duplicate.",
        )

    created: list[RosterShift] = []

    if has_date:
        # ---- Mode: date copy ----
        target = body.target_date
        delta_days = (target - source.date).days
        source_end_date = source.end_date or source.date
        new_end_date = source_end_date + timedelta(days=delta_days)
        new_shift = RosterShift(
            staff_id=source.staff_id,
            booking_id=None,
            date=target,
            end_date=new_end_date if new_end_date != target else None,
            start_time=source.start_time,
            end_time=source.end_time,
            shift_type=source.shift_type,
            status=ShiftStatus.SCHEDULED,
            notes=source.notes,
            intended_driver_type=source.intended_driver_type or "jockey",
            created_source="manual",
        )
        db.add(new_shift)
        db.flush()
        # Re-link bookings whose event time falls inside the copy's window.
        # _events_for_booking applies the back-date heuristic so flight 23:55
        # on D-1 anchors correctly when pickup_date is D.
        from auto_roster import _events_for_booking
        copy_start_dt = datetime.combine(target, source.start_time)
        copy_end_dt = datetime.combine(new_end_date, source.end_time)
        if copy_end_dt <= copy_start_dt:
            copy_end_dt = copy_end_dt + timedelta(days=1)
        for b in (source.bookings or []):
            for _et, edt in _events_for_booking(b):
                if copy_start_dt <= edt <= copy_end_dt:
                    db.add(ShiftBookingLink(shift_id=new_shift.id, booking_id=b.id))
                    break
        created.append(new_shift)
    else:
        # ---- Mode: staff fanout ----
        # Build the (staff_id, forced_intended_driver_type) write list.
        writes: list[tuple[Optional[int], Optional[str]]] = []
        seen_staff: set[int] = set()
        for sid in (body.staff_ids or []):
            if sid in seen_staff:
                continue  # de-dupe accidental double-tick
            if sid == source.staff_id:
                continue  # skip source's own staff to avoid identical row
            seen_staff.add(sid)
            validate_staff_assignment(db, sid)
            writes.append((sid, None))
        if body.add_unassigned_jockey:
            writes.append((None, "jockey"))
        if body.add_unassigned_fleet:
            writes.append((None, "fleet"))

        if not writes:
            raise HTTPException(
                status_code=422,
                detail="No effective targets after de-duplication (all staff_ids match source, or none provided).",
            )

        # Source's existing booking links — fanout copies inherit them as-is.
        existing_links = (
            db.query(ShiftBookingLink)
            .filter(ShiftBookingLink.shift_id == shift_id)
            .all()
        )
        existing_booking_ids = [link.booking_id for link in existing_links]

        for write_sid, forced_intended in writes:
            intended = forced_intended or (source.intended_driver_type or "jockey")
            if write_sid is not None and forced_intended is None:
                user = db.query(User).filter(User.id == write_sid).first()
                if user and getattr(user, "driver_type", None) in ("jockey", "fleet"):
                    intended = user.driver_type
                # Overlap guard — fanout target must not collide with existing.
                conflict = check_shift_overlap(
                    db, write_sid, source.date, source.start_time, source.end_time
                )
                if conflict:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Staff {write_sid} already has a shift overlapping "
                            f"{format_time(source.start_time)}-{format_time(source.end_time)} "
                            f"on {source.date.strftime('%d/%m/%Y')}."
                        ),
                    )
            new_shift = RosterShift(
                staff_id=write_sid,
                booking_id=None,
                date=source.date,
                end_date=source.end_date,
                start_time=source.start_time,
                end_time=source.end_time,
                shift_type=source.shift_type,
                status=ShiftStatus.SCHEDULED,
                notes=source.notes,
                intended_driver_type=intended,
                created_source="manual",
            )
            db.add(new_shift)
            db.flush()
            for bid in existing_booking_ids:
                db.add(ShiftBookingLink(shift_id=new_shift.id, booking_id=bid))
            created.append(new_shift)

    db.commit()
    for s in created:
        db.refresh(s)
    return [shift_to_response(s, db) for s in created]


@router.post("/roster/{shift_id}/merge", response_model=RosterShiftResponse)
async def merge_shift(
    shift_id: int,
    body: RosterShiftMergeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Merge a roster shift with an adjacent neighbour.

    Adjacency rule: neighbour's start equals this shift's end OR vice versa
    (touching exactly, gap = 0 minutes). Any other gap returns 422.

    Staff rule: same staff_id on both, OR exactly one is unassigned. Mixed
    different-staff shifts are not merged.

    Survivor: the earlier-starting shift. Result spans `[earlier.start,
    later.end]`. Booking links union onto the survivor; the loser row is
    deleted.
    """
    a = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    b = db.query(RosterShift).filter(RosterShift.id == body.other_shift_id).first()
    if not a or not b:
        raise HTTPException(status_code=404, detail="Shift not found")
    if a.id == b.id:
        raise HTTPException(status_code=422, detail="Cannot merge a shift with itself")

    a_start, a_end = _shift_window_dt(a)
    b_start, b_end = _shift_window_dt(b)
    earlier, later = (a, b) if a_start <= b_start else (b, a)
    e_start, e_end = _shift_window_dt(earlier)
    l_start, l_end = _shift_window_dt(later)

    # Adjacency: earlier.end == later.start exactly. Any gap > 0 → reject.
    if e_end != l_start:
        if e_end > l_start:
            raise HTTPException(status_code=422, detail="Shifts overlap; merge requires exact adjacency (gap = 0).")
        gap_minutes = int((l_start - e_end).total_seconds() / 60)
        raise HTTPException(
            status_code=422,
            detail=f"Shifts not adjacent (gap = {gap_minutes} min). Merge requires touching exactly.",
        )

    # Staff: same, or one null.
    if a.staff_id is not None and b.staff_id is not None and a.staff_id != b.staff_id:
        raise HTTPException(status_code=422, detail="Cannot merge shifts assigned to different staff.")
    survivor_staff = earlier.staff_id if earlier.staff_id is not None else later.staff_id

    # Apply to earlier (survivor).
    earlier.staff_id = survivor_staff
    earlier.end_time = later.end_time
    earlier.end_date = later.end_date or later.date
    if earlier.end_date == earlier.date:
        earlier.end_date = None
    # intended_driver_type: prefer the assigned side's; else preserve earlier's.
    if survivor_staff is not None:
        user = db.query(User).filter(User.id == survivor_staff).first()
        if user and getattr(user, "driver_type", None) in ("jockey", "fleet"):
            earlier.intended_driver_type = user.driver_type

    # Move loser's booking links onto survivor (skip duplicates).
    existing = {
        link.booking_id
        for link in db.query(ShiftBookingLink).filter(ShiftBookingLink.shift_id == earlier.id).all()
    }
    loser_links = db.query(ShiftBookingLink).filter(ShiftBookingLink.shift_id == later.id).all()
    for link in loser_links:
        if link.booking_id in existing:
            db.delete(link)
            continue
        link.shift_id = earlier.id
        existing.add(link.booking_id)

    db.delete(later)
    db.commit()
    db.refresh(earlier)
    return shift_to_response(earlier, db)


@router.post("/roster/{shift_id}/split", response_model=List[RosterShiftResponse])
async def split_shift(
    shift_id: int,
    body: RosterShiftSplitRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Split a shift in two at `split_at_time`.

    `split_at_time` ("HH:MM") must be strictly inside (start_time, end_time).
    Times equal to start or end return 422 (degenerate halves).

    For overnight shifts the split is interpreted in the shift's wall-clock
    window — a 22:00→02:00 (D→D+1) shift split at 00:00 yields halves
    [22:00, 00:00] (date=D, end_date=D+1) and [00:00, 02:00] (date=D+1).

    Booking links are re-distributed by event_time using right-inclusive
    semantics: an event at exactly `split_at_time` goes to the SECOND half.
    Events outside both halves' windows (shouldn't happen, but defensive)
    stay on the original/first half.
    """
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    split_t = parse_time_string(body.split_at_time)

    # Locate the split moment on the shift's wall-clock window.
    start_dt, end_dt = _shift_window_dt(shift)
    is_overnight = end_dt.date() != start_dt.date()

    # Pick the calendar date for the split moment: same day as start unless
    # the split clock-time has already passed today's end (so it must be the
    # next day) — handled by walking forward from start_dt.
    candidate = datetime.combine(start_dt.date(), split_t)
    if candidate <= start_dt:
        candidate = candidate + timedelta(days=1)
    split_dt = candidate

    if split_dt <= start_dt or split_dt >= end_dt:
        raise HTTPException(
            status_code=422,
            detail=(
                f"split_at_time must be strictly inside the shift window "
                f"({format_time(shift.start_time)}-{format_time(shift.end_time)})."
            ),
        )

    # First half: [start, split). Second half: [split, end].
    first_date = shift.date
    first_end_date = split_dt.date() if split_dt.date() != first_date else None
    second_date = split_dt.date()
    second_end_date = end_dt.date() if end_dt.date() != second_date else None

    # Build the second half as a new row first so we have an ID for re-linking.
    second = RosterShift(
        staff_id=shift.staff_id,
        booking_id=None,
        date=second_date,
        end_date=second_end_date,
        start_time=split_t,
        end_time=shift.end_time,
        shift_type=shift.shift_type,
        status=shift.status,
        notes=shift.notes,
        intended_driver_type=shift.intended_driver_type or "jockey",
        created_source=shift.created_source or "manual",
    )
    db.add(second)
    db.flush()

    # Apply the first half in place.
    shift.end_time = split_t
    shift.end_date = first_end_date

    # Re-distribute booking links by event_time. Right-inclusive at the cut.
    from auto_roster import _events_for_booking
    links = db.query(ShiftBookingLink).filter(ShiftBookingLink.shift_id == shift.id).all()
    for link in links:
        b = db.query(Booking).filter(Booking.id == link.booking_id).first()
        if not b:
            continue
        events = _events_for_booking(b)
        # Prefer the *latest* event that falls inside the original window —
        # if it's at-or-after split_dt, this booking belongs to the second half.
        belongs_to_second = False
        for _et, edt in events:
            if start_dt <= edt <= end_dt and edt >= split_dt:
                belongs_to_second = True
                break
        if belongs_to_second:
            link.shift_id = second.id

    db.commit()
    db.refresh(shift)
    db.refresh(second)
    return [shift_to_response(shift, db), shift_to_response(second, db)]


@router.patch("/roster/{shift_id}/unassign", response_model=RosterShiftResponse)
async def unassign_shift(
    shift_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Set staff_id = NULL on a shift. Idempotent — already-unassigned shifts
    return 200 with the unchanged row. Status, times, links untouched.

    Thin wrapper over the existing PUT /roster/{id} explicit-null flow (added
    2026-04-06 with the staff_id_provided pattern); the v3 Calendar action bar
    calls this dedicated endpoint so the admin's intent is unambiguous.
    """
    shift = db.query(RosterShift).filter(RosterShift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")

    if shift.staff_id is None:
        return shift_to_response(shift, db)

    shift.staff_id = None
    db.commit()
    db.refresh(shift)
    return shift_to_response(shift, db)


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


@router.get("/employee/team-shifts", response_model=List[TeamShiftResponse])
async def get_team_shifts(
    date_from: Optional[date_type] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[date_type] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    week_start: Optional[date_type] = Query(None, description="Filter by week starting date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """View-only feed of teammates' shifts for the Employee calendar.

    Excludes the requester's own shifts (those come from /api/employee/shifts)
    and unassigned shifts (those come from /api/employee/available-shifts).
    Returns a deliberately stripped shape — initials, name, phone, date, hours
    — so a future bug can't render bookings/notes/customer details on the
    Employee page.
    """
    query = db.query(RosterShift).filter(
        RosterShift.staff_id.isnot(None),
        RosterShift.staff_id != current_user.id,
    )

    # Apply date filters (include overnight shifts that end in range)
    if date_from and date_to:
        query = query.filter(
            or_(
                and_(RosterShift.date >= date_from, RosterShift.date <= date_to),
                and_(RosterShift.end_date >= date_from, RosterShift.end_date <= date_to),
            )
        )
    elif week_start:
        week_end = week_start + timedelta(days=6)
        query = query.filter(
            or_(
                and_(RosterShift.date >= week_start, RosterShift.date <= week_end),
                and_(RosterShift.end_date >= week_start, RosterShift.end_date <= week_end),
            )
        )

    shifts = query.order_by(RosterShift.date, RosterShift.start_time).all()

    # Driver-type relevance filter (locked 2026-04-30):
    #   jockey users see all teammates (mixed pool)
    #   fleet  users see only fleet teammates
    user_driver_type = getattr(current_user, "driver_type", None)

    def _visible(s):
        if s.staff is None:
            return False
        if user_driver_type == "jockey":
            return True
        if user_driver_type == "fleet":
            return getattr(s.staff, "driver_type", None) == "fleet"
        return False  # admin / undefined → no team feed

    return [
        TeamShiftResponse(
            initials=get_staff_initials(s.staff),
            first_name=s.staff.first_name,
            last_name=s.staff.last_name,
            phone=normalise_uk_phone(s.staff.phone),
            date=s.date,
            end_date=s.end_date or s.date,
            start_time=format_time(s.start_time),
            end_time=format_time(s.end_time),
        )
        for s in shifts
        if _visible(s)
    ]


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
    """Unassigned shifts the current user is eligible to claim.

    Filter rule (locked 2026-04-30):
      jockey users see all unassigned shifts (jockey- and fleet-intended)
      fleet  users see only fleet-intended unassigned shifts

    Anyone without a driver_type (e.g. admins not configured as drivers)
    sees nothing — they shouldn't be claiming jockey/fleet work anyway.
    """
    today = date_type.today()

    query = db.query(RosterShift).filter(
        RosterShift.staff_id.is_(None),
        RosterShift.date >= today,
        RosterShift.status != ShiftStatus.CANCELLED,
        # Self-contained: auto-created shifts live only on the Planner Calendar
        # for now and aren't claimable until the admin promotes them.
        RosterShift.created_source != "auto",
    )

    user_driver_type = getattr(current_user, "driver_type", None)
    if user_driver_type == "fleet":
        query = query.filter(RosterShift.intended_driver_type == "fleet")
    elif user_driver_type != "jockey":
        # No driver_type set → not a driver → no claimable shifts.
        return []

    shifts = query.order_by(RosterShift.date, RosterShift.start_time).all()
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
    "gap_max_minutes": 150,
    "mixed_gap_max_minutes": 150,
    "start_buffer_minutes": 20,
    "end_buffer_minutes": 30,
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
        .filter(User.is_active == True)
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
# Phase 3 — additive commit + undo (locked rules per SPEC.md 2026-04-24)
#   - Writes ONLY new shifts on empty slots (no overwrites).
#   - Each created row carries planner_run_id + created_source='planner'.
#   - Undo = DELETE WHERE planner_run_id = ? AND status = 'scheduled'
#     (CONFIRMED engine shifts are deliberately excluded from undo).
#   - QA-only: defence-in-depth gate via require_qa_admin.
#   - Audit: PLANNER_RUN_COMMITTED / PLANNER_RUN_UNDONE.
# =====================================================================================


def _shifts_overlap_for_staff(
    db: Session,
    *,
    staff_id: int,
    shift_date: date_type,
    end_date: Optional[date_type],
    start_time: time,
    end_time: time,
) -> Optional[RosterShift]:
    """Return any existing shift for this staff that overlaps the proposal.

    Same-day match is the common case; for overnight proposals (end_date >
    date) the check fans across both dates so we don't write a Mon 22:00 →
    Tue 02:00 shift on top of someone's Tue 00:00 → Tue 06:00.
    """
    candidate_dates = {shift_date}
    if end_date and end_date != shift_date:
        candidate_dates.add(end_date)
    existing = (
        db.query(RosterShift)
        .filter(
            RosterShift.staff_id == staff_id,
            or_(
                RosterShift.date.in_(candidate_dates),
                RosterShift.end_date.in_(candidate_dates),
            ),
        )
        .all()
    )
    for s in existing:
        # Same-day strict overlap — for overnight cases we approximate by
        # treating any shift on the same date as a candidate (Phase 3 is
        # additive only; if the admin really wants to overwrite they must
        # delete the existing shift manually first).
        if start_time < (s.end_time) and end_time > (s.start_time):
            return s
        # Cross-day adjacency: existing covers candidate's tail / head
        if end_date and end_date != shift_date and s.date == end_date:
            if s.start_time < end_time:
                return s
        if s.end_date and s.end_date != s.date and s.end_date == shift_date:
            if s.end_time > start_time:
                return s
    return None


def _audit_planner(
    db: Session,
    *,
    event: AuditLogEvent,
    user: User,
    run_id: str,
    payload: dict,
) -> None:
    """Append-only audit row for planner commit / undo."""
    try:
        log = AuditLog(
            session_id=f"planner-{run_id}",
            booking_reference=None,
            event=event,
            event_data=json.dumps({
                "run_id": run_id,
                "by_user_id": user.id,
                "by_user_email": user.email,
                **payload,
            }),
        )
        db.add(log)
    except Exception:
        # Never fail the operation because of an audit write.
        pass


@router.post(
    "/admin/qa/roster-planner/commit",
    response_model=PlannerCommitResponse,
)
async def commit_planner_run(
    request: PlannerCommitRequest,
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Commit selected proposals from a recorded run as new roster_shifts.

    Phase 3 semantics (locked):
      - Only `kind='new'` proposals are eligible. `extend` and
        `untouched_for_reason` are rejected.
      - Each created row carries `planner_run_id` + `created_source='planner'`.
      - For each proposal's events, a `ShiftBookingLink` row is created so
        the shift covers the customer's drop-off / pick-up.
      - If any selected proposal overlaps an existing shift for the same
        staff_id, the entire request fails with 409 — atomic.
      - Defensive: same proposal_index requested twice in the body is rejected.

    Body:
      - run_id: str — must reference an existing planner_runs row
      - proposal_indexes: list[int] — positions in the run's proposed_shifts
    """
    from db_models import PlannerRun, AuditLog as _AuditLogImported  # noqa: F401

    run = db.query(PlannerRun).filter(PlannerRun.run_id == request.run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {request.run_id} not found")
    if not run.proposal_json:
        raise HTTPException(status_code=400, detail="Run has no proposal payload")

    try:
        proposal = json.loads(run.proposal_json)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Run proposal_json corrupt: {exc}")

    proposed_shifts = proposal.get("proposed_shifts", [])

    # Reject duplicate indexes early so we don't commit the same proposal twice.
    seen: set[int] = set()
    for idx in request.proposal_indexes:
        if idx in seen:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate proposal_index {idx}",
            )
        seen.add(idx)

    # Validate every requested index before doing any writes (atomicity).
    selected: list[dict] = []
    for idx in request.proposal_indexes:
        if idx < 0 or idx >= len(proposed_shifts):
            raise HTTPException(
                status_code=400,
                detail=f"proposal_index {idx} out of range (0..{len(proposed_shifts) - 1})",
            )
        ps = proposed_shifts[idx]
        if ps.get("kind") != "new":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"proposal_index {idx} has kind={ps.get('kind')!r}; "
                    "Phase 3 commits only kind='new' proposals."
                ),
            )
        selected.append(ps)

    # Reject Phase 3.6+ override actions early — surfaces "not yet supported"
    # to the FE instead of silently dropping the override.
    for idx, override in (request.overrides or {}).items():
        if override.action in ("merge", "split"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Override action '{override.action}' not yet supported on commit "
                    f"(Phase 3.6 work). Use feedback-only for now."
                ),
            )

    # Reject re-commits of a proposal_index that already has live shifts in
    # this run — Phase 3 commits each proposal once. Without this guard a
    # second commit silently re-writes the original row and any duplicates,
    # producing ghost shifts (May 2026: proposal 50 ended up with 3 rows
    # because three commits stacked).
    prior_committed: set[int] = set()
    prior_audits = (
        db.query(AuditLog)
        .filter(
            AuditLog.session_id == f"planner-{request.run_id}",
            AuditLog.event == AuditLogEvent.PLANNER_RUN_COMMITTED,
        )
        .all()
    )
    live_shift_ids = {
        s.id
        for s in db.query(RosterShift)
        .filter(RosterShift.planner_run_id == request.run_id)
        .all()
    }
    for audit_row in prior_audits:
        try:
            payload = json.loads(audit_row.event_data or "{}")
        except (TypeError, ValueError):
            continue
        for k, v in (payload.get("proposal_to_shift_ids") or {}).items():
            try:
                pi = int(k)
            except (TypeError, ValueError):
                continue
            if isinstance(v, list) and any(
                isinstance(sid, int) and sid in live_shift_ids for sid in v
            ):
                prior_committed.add(pi)
    already = sorted(set(request.proposal_indexes) & prior_committed)
    if already:
        raise HTTPException(
            status_code=409,
            detail=(
                f"proposal_index(es) {already} already committed in this run. "
                "Undo the run first if you want to re-commit, or edit the "
                "live shift directly via the roster admin UI."
            ),
        )

    created_ids: list[int] = []
    applied_overrides: list[dict] = []  # for audit
    # Per-proposal mapping so the GET-detail endpoint can attribute live
    # shifts back to their source proposal precisely. Bucketing by
    # (date, start, end) collides when the engine plans multiple shifts
    # in the same time window — see the duplicate-fleet bug from May 2026.
    proposal_to_shift_ids: dict[int, list[int]] = {}
    try:
        for idx, ps in zip(request.proposal_indexes, selected):
            override = request.overrides.get(idx) if request.overrides else None

            # ---- Action: delete → skip writing this proposal entirely. ----
            if override and override.action == "delete":
                applied_overrides.append({
                    "proposal_index": idx,
                    "action": "delete",
                    "shift_ids": [],
                })
                proposal_to_shift_ids[idx] = []
                continue

            shift_date = date_type.fromisoformat(ps["date"]) if isinstance(ps["date"], str) else ps["date"]
            end_date_val = ps.get("end_date")
            if end_date_val and isinstance(end_date_val, str):
                end_date_val = date_type.fromisoformat(end_date_val)
            start_t = parse_time_string(ps["start_time"]) if isinstance(ps["start_time"], str) else ps["start_time"]
            end_t = parse_time_string(ps["end_time"]) if isinstance(ps["end_time"], str) else ps["end_time"]
            staff_id = ps.get("staff_id")  # may be None (unassigned shift)

            # ---- Action: unassign → drop staff_id to None. ----
            if override and override.action == "unassign":
                staff_id = None

            # ---- Action: duplicate → original staff_id + each target staff. ----
            # Original staff_id can be None (admin chose to fan out an
            # unassigned proposal); we still write one row per target.
            # Each entry is (staff_id, intended_driver_type_override) — the
            # override is only set for explicit unassigned-jockey / -fleet
            # extras so we can tag those rows correctly without a user lookup.
            writes: list[tuple[Optional[int], Optional[str]]] = [(staff_id, None)]
            if override and override.action == "duplicate":
                has_targets = bool(override.target_staff_ids)
                wants_extra_jockey = bool(getattr(override, "add_unassigned_jockey", False))
                wants_extra_fleet = bool(getattr(override, "add_unassigned_fleet", False))
                if not (has_targets or wants_extra_jockey or wants_extra_fleet):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"duplicate override at index {idx} requires target_staff_ids "
                            "or add_unassigned_jockey / add_unassigned_fleet"
                        ),
                    )
                # de-dupe in case admin ticks the same staff twice; skip
                # original staff_id so we don't double-write the same row.
                seen_targets: set[int] = set()
                for tid in (override.target_staff_ids or []):
                    if tid == staff_id or tid in seen_targets:
                        continue
                    seen_targets.add(tid)
                    writes.append((tid, None))
                if wants_extra_jockey:
                    writes.append((None, "jockey"))
                if wants_extra_fleet:
                    writes.append((None, "fleet"))

            shift_type_str = ps.get("shift_type", "morning")
            this_proposal_shift_ids: list[int] = []
            for write_staff_id, forced_intended in writes:
                # Phase 3 conflict check — only meaningful when staff is assigned.
                if write_staff_id is not None:
                    conflict = _shifts_overlap_for_staff(
                        db,
                        staff_id=write_staff_id,
                        shift_date=shift_date,
                        end_date=end_date_val,
                        start_time=start_t,
                        end_time=end_t,
                    )
                    if conflict is not None:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"Proposal at {shift_date} {start_t.strftime('%H:%M')}-"
                                f"{end_t.strftime('%H:%M')} for staff_id={write_staff_id} "
                                f"overlaps existing shift id={conflict.id} "
                                f"({conflict.start_time.strftime('%H:%M')}-"
                                f"{conflict.end_time.strftime('%H:%M')}). "
                                "Phase 3 is additive only — resolve manually or wait for Phase 4."
                            ),
                        )

                # intended_driver_type follows the assigned user's
                # driver_type when present (so a duplicate-to-fleet
                # automatically tags the new row 'fleet'). For unassigned
                # writes (engine output without override, or unassign
                # override), default to 'jockey' since the engine only
                # auto-creates jockey work — except when the duplicate
                # override explicitly asks for an unassigned-fleet row.
                row_intended = forced_intended or "jockey"
                if write_staff_id is not None and forced_intended is None:
                    target_user = db.query(User).filter(User.id == write_staff_id).first()
                    if target_user and getattr(target_user, "driver_type", None) in ("jockey", "fleet"):
                        row_intended = target_user.driver_type

                new_shift = RosterShift(
                    staff_id=write_staff_id,
                    date=shift_date,
                    end_date=end_date_val or shift_date,
                    start_time=start_t,
                    end_time=end_t,
                    shift_type=ShiftType(shift_type_str),
                    status=ShiftStatus.SCHEDULED,
                    notes=ps.get("reason"),
                    created_source="planner",
                    planner_run_id=request.run_id,
                    intended_driver_type=row_intended,
                )
                db.add(new_shift)
                db.flush()  # populate new_shift.id
                created_ids.append(new_shift.id)
                this_proposal_shift_ids.append(new_shift.id)

                for event in ps.get("events") or []:
                    booking_id = event.get("booking_id")
                    if booking_id is None:
                        continue
                    # Defensive: skip if a link already exists.
                    existing_link = (
                        db.query(ShiftBookingLink)
                        .filter(
                            ShiftBookingLink.shift_id == new_shift.id,
                            ShiftBookingLink.booking_id == booking_id,
                        )
                        .first()
                    )
                    if existing_link:
                        continue
                    db.add(ShiftBookingLink(shift_id=new_shift.id, booking_id=booking_id))

            proposal_to_shift_ids[idx] = this_proposal_shift_ids
            if override:
                applied_overrides.append({
                    "proposal_index": idx,
                    "action": override.action,
                    "shift_ids": list(this_proposal_shift_ids),
                    "target_staff_ids": override.target_staff_ids,
                    "add_unassigned_jockey": getattr(override, "add_unassigned_jockey", False),
                    "add_unassigned_fleet": getattr(override, "add_unassigned_fleet", False),
                })

        _audit_planner(
            db,
            event=AuditLogEvent.PLANNER_RUN_COMMITTED,
            user=current_user,
            run_id=request.run_id,
            payload={
                "shifts_created": len(created_ids),
                "shift_ids": created_ids,
                "proposal_indexes": request.proposal_indexes,
                "applied_overrides": applied_overrides,
                # Authoritative per-proposal mapping. GET-detail reads this
                # back to avoid the (date,start,end) bucketing collision.
                "proposal_to_shift_ids": {str(k): v for k, v in proposal_to_shift_ids.items()},
            },
        )

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Commit failed: {exc}")

    return PlannerCommitResponse(
        run_id=request.run_id,
        shifts_created=len(created_ids),
        shift_ids=created_ids,
    )


@router.delete(
    "/admin/qa/roster-planner/runs/{run_id}",
    response_model=PlannerUndoResponse,
)
async def undo_planner_run(
    run_id: str,
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Undo a committed run by deleting its engine-created scheduled shifts.

    Idempotent — a run that was never committed (or already undone) returns
    `shifts_deleted=0` with no error.

    Locked rules:
      - Only deletes `status = 'scheduled'` rows. Once a shift becomes
        CONFIRMED (jockey accepted, etc.) it is permanently the saved
        roster's responsibility — undo can't pull it back.
      - `shift_booking_links` cascade-delete via the FK, so customer
        bookings are simply unlinked, not deleted.
    """
    targets = (
        db.query(RosterShift)
        .filter(
            RosterShift.planner_run_id == run_id,
            RosterShift.status == ShiftStatus.SCHEDULED,
        )
        .all()
    )
    deleted_ids: list[int] = []

    try:
        for shift in targets:
            # Remove links first so we don't rely on FK cascade behaviour
            # (which is set up via UniqueConstraint, not ON DELETE on the
            # SQLAlchemy mapping in all cases — be explicit).
            db.query(ShiftBookingLink).filter(
                ShiftBookingLink.shift_id == shift.id
            ).delete(synchronize_session=False)
            deleted_ids.append(shift.id)
            db.delete(shift)

        _audit_planner(
            db,
            event=AuditLogEvent.PLANNER_RUN_UNDONE,
            user=current_user,
            run_id=run_id,
            payload={
                "shifts_deleted": len(deleted_ids),
                "shift_ids": deleted_ids,
            },
        )

        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Undo failed: {exc}")

    return PlannerUndoResponse(run_id=run_id, shifts_deleted=len(deleted_ids))


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

    # Compute committed_indexes + committed_shifts_by_index — proposal
    # positions that currently have at least one matching roster_shift for
    # this run, and the *live* state of each (snapshot includes any
    # post-commit overrides like unassign + any subsequent claims).
    #
    # Source of truth: PLANNER_RUN_COMMITTED audit-log rows for this run.
    # Each commit records `proposal_to_shift_ids` so we can attribute live
    # shifts back to their source proposal precisely. Bucketing by
    # (date, start, end) collides when the engine plans multiple shifts in
    # the same time window (e.g. duplicate-fleet on one shows another
    # proposal's KW too) — see May 2026 bug report.
    committed_indexes: list[int] = []
    committed_shifts_by_index: dict[int, list[CommittedShiftSnapshot]] = {}
    if proposal and proposal.get("proposed_shifts"):
        # Aggregate proposal_index → set of shift_ids across every commit
        # that's happened on this run (multiple commits can stack).
        idx_to_shift_ids: dict[int, set[int]] = {}
        commit_audits = (
            db.query(AuditLog)
            .filter(
                AuditLog.session_id == f"planner-{run_id}",
                AuditLog.event == AuditLogEvent.PLANNER_RUN_COMMITTED,
            )
            .order_by(AuditLog.created_at.asc())
            .all()
        )
        for audit_row in commit_audits:
            try:
                payload = json.loads(audit_row.event_data or "{}")
            except (TypeError, ValueError):
                continue
            mapping = payload.get("proposal_to_shift_ids") or {}
            for k, v in mapping.items():
                try:
                    pi = int(k)
                except (TypeError, ValueError):
                    continue
                if not isinstance(v, list):
                    continue
                idx_to_shift_ids.setdefault(pi, set()).update(int(x) for x in v if isinstance(x, int))

        # Cross-reference with currently-live shifts so undo / manual delete
        # is reflected. Live = exists in DB and still belongs to this run.
        live_by_id: dict[int, RosterShift] = {
            s.id: s
            for s in db.query(RosterShift)
            .filter(RosterShift.planner_run_id == run_id)
            .all()
        }

        for idx in sorted(idx_to_shift_ids.keys()):
            live_for_idx = [
                live_by_id[sid]
                for sid in sorted(idx_to_shift_ids[idx])
                if sid in live_by_id
            ]
            if not live_for_idx:
                continue
            committed_indexes.append(idx)
            committed_shifts_by_index[idx] = [
                CommittedShiftSnapshot(
                    shift_id=s.id,
                    staff_id=s.staff_id,
                    staff_initials=get_staff_initials(s.staff) if s.staff else None,
                    status=s.status.value if hasattr(s.status, "value") else str(s.status),
                    intended_driver_type=(
                        s.intended_driver_type
                        if isinstance(getattr(s, "intended_driver_type", None), str)
                        else None
                    ),
                )
                for s in live_for_idx
            ]

        # Backward-compat: if no commit audit ever recorded a per-proposal
        # mapping (run was committed before the fix), fall back to the old
        # (date, start, end) bucketing so the FE doesn't go blank.
        if not committed_shifts_by_index:
            committed_shifts = (
                db.query(RosterShift)
                .filter(RosterShift.planner_run_id == run_id)
                .all()
            )
            shifts_by_key: dict[tuple, list[RosterShift]] = {}
            for s in committed_shifts:
                shifts_by_key.setdefault(
                    (s.date, s.start_time, s.end_time), []
                ).append(s)
            for idx, ps in enumerate(proposal["proposed_shifts"]):
                ps_date = date_type.fromisoformat(ps["date"]) if isinstance(ps["date"], str) else ps["date"]
                ps_start = parse_time_string(ps["start_time"]) if isinstance(ps["start_time"], str) else ps["start_time"]
                ps_end = parse_time_string(ps["end_time"]) if isinstance(ps["end_time"], str) else ps["end_time"]
                matched = shifts_by_key.get((ps_date, ps_start, ps_end))
                if not matched:
                    continue
                committed_indexes.append(idx)
                committed_shifts_by_index[idx] = [
                    CommittedShiftSnapshot(
                        shift_id=s.id,
                        staff_id=s.staff_id,
                        staff_initials=get_staff_initials(s.staff) if s.staff else None,
                        status=s.status.value if hasattr(s.status, "value") else str(s.status),
                        intended_driver_type=(
                            s.intended_driver_type
                            if isinstance(getattr(s, "intended_driver_type", None), str)
                            else None
                        ),
                    )
                    for s in matched
                ]

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
        committed_indexes=committed_indexes,
        committed_shifts_by_index=committed_shifts_by_index,
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

    override_json = None
    if payload.override is not None:
        # Stored as JSON text — see PlannerRunFeedback.override_json docstring.
        override_json = json.dumps(payload.override.model_dump(mode="json"))

    row = PlannerRunFeedback(
        run_id=run_id,
        shift_date=payload.shift_date,
        shift_start_time=payload.shift_start_time,
        shift_end_time=payload.shift_end_time,
        shift_staff_id=payload.shift_staff_id,
        proposed_shift_index=payload.proposed_shift_index,
        severity=payload.severity,
        comment=payload.comment,
        override_json=override_json,
        submitted_by=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _feedback_row_to_response(row)


def _feedback_row_to_response(row) -> PlannerRunFeedbackResponse:
    """Hydrate the JSON-stored override back into the typed response."""
    override = None
    if row.override_json:
        try:
            override = PlannerRunFeedbackOverride.model_validate(json.loads(row.override_json))
        except (ValueError, TypeError):
            override = None
    return PlannerRunFeedbackResponse(
        id=row.id,
        run_id=row.run_id,
        shift_date=row.shift_date,
        shift_start_time=row.shift_start_time,
        shift_end_time=row.shift_end_time,
        shift_staff_id=row.shift_staff_id,
        proposed_shift_index=row.proposed_shift_index,
        severity=row.severity,
        comment=row.comment,
        override=override,
        submitted_by=row.submitted_by,
        submitted_at=row.submitted_at,
    )


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
    rows = q.order_by(PlannerRunFeedback.submitted_at.desc()).limit(limit).all()
    return [_feedback_row_to_response(r) for r in rows]


# ============================================================================
# POST /api/admin/qa/roster-planner/regenerate-auto
#
# Operator-triggered "(Re)generate auto-roster" — runs the live auto_roster
# logic against every CONFIRMED booking with events in the chosen date set.
# Replaces the shadow-mode "Run engine now" workflow as the primary affordance
# on the Planner page (the engine endpoint at /propose stays for QA replay).
# ============================================================================

from pydantic import BaseModel, Field, field_validator  # noqa: E402


class RegenerateAutoRequest(BaseModel):
    """Body for /admin/qa/roster-planner/regenerate-auto.

    `mode` controls how the date set is derived:
      - `next_4_weeks`: rolling window from today.date() to today + window_days.
      - `date_range`: requires `date_from` and `date_to` (inclusive).
      - `individual_dates`: requires `dates` (list of explicit dates).

    `force_rebuild`: if True, delete every auto-shift in the chosen scope that
    is still SCHEDULED + unassigned BEFORE rebuilding. Sharp edge — wipes any
    in-progress admin edits to those shifts. Off by default.
    """

    mode: str = Field(..., description="next_4_weeks | date_range | individual_dates")
    date_from: Optional[date_type] = None
    date_to: Optional[date_type] = None
    dates: Optional[List[date_type]] = None
    force_rebuild: bool = False

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v):
        if v not in ("next_4_weeks", "date_range", "individual_dates"):
            raise ValueError("mode must be next_4_weeks, date_range or individual_dates")
        return v


def _resolve_dates(req: RegenerateAutoRequest, settings: PlannerSettings) -> set[date_type]:
    """Map a regenerate request to the explicit date set the run will cover."""
    today = datetime.now(UK_TZ).date()
    if req.mode == "next_4_weeks":
        return {today + timedelta(days=i) for i in range(settings.window_days)}
    if req.mode == "date_range":
        if not req.date_from or not req.date_to:
            raise HTTPException(status_code=422, detail="date_range mode requires date_from and date_to")
        if req.date_to < req.date_from:
            raise HTTPException(status_code=422, detail="date_to must be >= date_from")
        days = (req.date_to - req.date_from).days
        return {req.date_from + timedelta(days=i) for i in range(days + 1)}
    # individual_dates
    if not req.dates:
        raise HTTPException(status_code=422, detail="individual_dates mode requires a non-empty `dates` list")
    return set(req.dates)


@router.post("/admin/qa/roster-planner/regenerate-auto")
async def regenerate_auto_roster(
    req: RegenerateAutoRequest,
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Operator entry point for "(Re)generate auto-roster".

    2026-05-02 refactor — uses `rebuild_auto_for_dates`, which clusters
    events with the engine's `group_events_by_gap` (consecutive-event
    semantics) instead of edge-based extension. Untouched auto-shifts on
    target dates are always wiped before recreation; admin-claimed /
    confirmed auto-shifts are preserved untouched. The `force_rebuild`
    flag on the request is now informational only — every regenerate is
    a clean rebuild for the days in scope.

    Returns counts so the UI can render a "X created, Y deleted" banner.
    """
    # Defensive import: a partial / lagging deploy where db_models.py and
    # auto_roster.py are out of sync raises ImportError here. Catch it and
    # return a clean 503 so the UI surfaces the actual cause instead of
    # CORS-masked 500.
    try:
        from auto_roster import rebuild_auto_for_dates
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Auto-roster module unavailable on the current backend deploy "
                f"({e}). Ask an engineer to redeploy the backend service."
            ),
        )

    parsed = _load_planner_settings_rows(db)
    settings = PlannerSettings.from_kv(parsed)
    target_dates = _resolve_dates(req, settings)
    if not target_dates:
        return {
            "deleted": 0, "created": 0, "extended": 0, "skipped": 0,
            "bookings_processed": 0, "dates_covered": 0,
        }

    result = rebuild_auto_for_dates(db, target_dates, settings)
    return {
        "deleted": result.get("deleted", 0),
        "created": result.get("created", 0),
        # Kept for backwards compat with the existing UI banner — extend
        # is no longer a separate operation, but the field stays so the
        # frontend doesn't need to change.
        "extended": 0,
        "skipped": 0,
        "bookings_processed": result.get("bookings_in_scope", 0),
        "dates_covered": len(target_dates),
    }


@router.delete("/admin/qa/roster-planner/auto-shifts")
async def delete_all_auto_shifts_endpoint(
    current_user: User = Depends(require_qa_admin),
    db: Session = Depends(get_db),
):
    """Admin override: wipe every untouched auto-shift across all dates.

    Touched / claimed auto-shifts are left intact. Useful for "I don't
    trust the current state of the auto-roster, let me start fresh" —
    and after this runs, the next booking confirmation (or a regenerate
    call) will repopulate cleanly.
    """
    try:
        from auto_roster import delete_all_auto_shifts
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Auto-roster module unavailable on the current backend deploy "
                f"({e}). Ask an engineer to redeploy the backend service."
            ),
        )

    count = delete_all_auto_shifts(db)
    return {"deleted": count}
