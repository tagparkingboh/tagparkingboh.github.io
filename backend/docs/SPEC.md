# TAG Parking Development Spec

## Standards & Conventions

### Timezone & Date/Time Formats

- **All UI displays and DB records must be in UK timezone** (`Europe/London`)
- **Date format**: `DD/MM/YYYY` (e.g., `02/03/2026`)
- **Date input**: User enters `02032026` → UI displays `02/03/2026`
- **Time format**: 24-hour clock (e.g., `23:59`)
- **Time input**: User enters `2359` → UI displays `23:59`

### Testing Requirements

For **every feature**, the following tests are required:

| Type | Description |
|------|-------------|
| Mocked Unit Tests | Test individual functions/logic in isolation |
| Mocked Integration Tests | Test API endpoints with mocked dependencies |

**Test Coverage Categories:**
1. **Happy path** - Successful scenarios
2. **Unhappy path** - Error scenarios, validation failures
3. **Edge cases** - Boundary conditions, limits, null values
4. **Boundaries** - Min/max values, date boundaries, time boundaries

---

## Database Access

### Environment URLs (from `.env`)

```
# Staging
DATABASE_URL=postgresql://postgres:oviYXmjpSwWKHejteMgdIxXTorTtGdUl@switchback.proxy.rlwy.net:25567/railway

# Production
DATABASE_URL=postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway
```

### Useful Queries

#### Check Booking Status Counts
```bash
DATABASE_URL="<url>" python3 -c "
from database import SessionLocal
from db_models import Booking
from sqlalchemy import func

db = SessionLocal()
status_counts = db.query(Booking.status, func.count(Booking.id)).group_by(Booking.status).all()
for status, count in sorted(status_counts, key=lambda x: -x[1]):
    print(f'{status}: {count}')
db.close()
"
```

#### Check Cancelled Bookings
```bash
DATABASE_URL="<url>" python3 -c "
from database import SessionLocal
from db_models import Booking, BookingStatus

db = SessionLocal()
cancelled = db.query(Booking).filter(Booking.status == BookingStatus.CANCELLED).count()
print(f'Cancelled: {cancelled}')
db.close()
"
```

#### Check Employee Holidays
```bash
DATABASE_URL="<url>" python3 -c "
from database import SessionLocal
from db_models import EmployeeHoliday

db = SessionLocal()
holidays = db.query(EmployeeHoliday).all()
for h in holidays:
    print(f'{h.employee_id}: {h.start_date} to {h.end_date} ({h.holiday_type})')
db.close()
"
```

#### Check Roster Shifts
```bash
DATABASE_URL="<url>" python3 -c "
from database import SessionLocal
from db_models import RosterShift
from datetime import date

db = SessionLocal()
shifts = db.query(RosterShift).filter(RosterShift.date >= date.today()).all()
for s in shifts:
    print(f'{s.date} {s.start_time}-{s.end_time}: {s.employee_id or \"Unassigned\"}')
db.close()
"
```

---

## Deprecated / Legacy Code

### capacity_tier (flight_departures table)

The `capacity_tier` and `is_call_us_only` fields in `FlightDeparture` model are **no longer used**. This was from an earlier approach where each flight had per-slot capacity limits.

**Current approach:** Capacity is now controlled solely by `MAX_PARKING_SPOTS = 50` in `booking_service.py`. All flights are bookable online up to the parking lot limit.

The legacy code remains in:
- `BookingsNew.jsx` - `isCallUsOnly` logic (always false in practice)
- `main.py` - Various endpoints still reference `capacity_tier`
- `db_models.py` - `FlightDeparture.capacity_tier` column

This can be cleaned up in a future refactor.

---

## Mistakes Log

### 2026-04-04

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Abandoned carts cache not refreshing | Frontend `fetchAbandonedCarts()` didn't pass `refresh=true` to bypass 1-hour cache | Added `refresh` param, button now passes `refresh=true` |
| Recent abandoned list showing old sessions | DB query had no ORDER BY, so older records filled the 100-slot limit first | Added `.order_by(AuditLog.created_at.desc())` |
| Fun Facts times not in UK timezone | `created_at` timestamps (UTC) compared/displayed without timezone conversion | Convert to UK timezone before comparing `.time()` and formatting |

### 2026-04-06

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Audit logs date filter using user's local timezone | `ukDateTimeToIso()` created ISO string without timezone, interpreted as local time | Convert UK datetime input to UTC using `Intl.DateTimeFormat` to get correct offset |
| Admin can't unassign shift (set staff_id to null) | `RosterShiftUpdate` model couldn't distinguish "not provided" from "explicitly null" | Added `staff_id_provided` flag with `model_validator` to track explicit null |

### 2026-04-08

| Issue | Root Cause | Fix |
|-------|------------|-----|
| Session tracking manual bookings missing phone/walk-in | Query only filtered for `['manual', 'admin']` booking sources | Added `'phone'` and `'walk-in'` to `booking_source.in_()` filter |

---

## Session Log

### 2026-04-08

**Features:**
- Removed car make/model library from booking flow - now relies solely on DVLA API (returns make + colour)
- Vehicle model field is now optional/nullable in database
- Simplified vehicle form: registration → DVLA lookup → make + colour auto-filled
- Weekly hours breakdown on Admin Calendar and Employee page
  - Collapsible weeks (Mon-Sun) with carets
  - Monthly totals section
  - Employee page shows only own hours

**Bug Fixes:**
- Session tracking now counts all non-online booking sources (manual, admin, phone, walk-in)

**Tests Added:** 55+ new tests
- `test_session_tracking.py` - TestManualBookingSourceTypes (6), TestManualBookingMock (5)
- `test_session_tracking_integration.py` - TestManualBookingSources (8)
- `test_vehicle_model_optional.py` - 20 tests for model-optional behavior
- `test_weekly_hours_breakdown.py` - 16 tests for weekly hours feature

**Commits:** (pending)

### 2026-04-06

**Features:**
- Added booking target milestones (55, 60 weekly; 125, 150 monthly)

**Bug Fixes:**
- Audit logs date filter now correctly uses UK timezone
- Admin can now unassign shifts by setting staff_id to null

**Tests Added:** 35 new tests
- `test_shift_unassign.py` (19)
- `test_shift_unassign_integration.py` (16)

**Commits:** `e4a367c` → (pending)

### 2026-04-04

**Features:**
- Employee shift self-service (claim/release)
- Employee holidays on calendar view
- Collapsible sections in roster calendar
- Available shifts horizontal card layout

**Bug Fixes:**
- Abandoned carts cache refresh bypass
- Recent abandoned list ordering
- Fun facts UK timezone display

**Tests Added:** 157 new tests
- `test_shift_claim_release.py` (31)
- `test_shift_claim_release_integration.py` (31)
- `test_employee_holidays.py` (20)
- `test_abandoned_carts.py` (34)
- `test_abandoned_carts_integration.py` (41)

**Commits:** `813f8e3` → `56e219e`
