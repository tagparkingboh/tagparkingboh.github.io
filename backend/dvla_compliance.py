"""DVLA compliance status semantics — single source of truth.

DVLA's Vehicle Enquiry Service returns small string enums for `taxStatus`
and `motStatus`. We persist the raw strings on `vehicles` so the frontend
can colour-code per value. This module encodes which exact values count
as "alert Kristian" vs benign — kept here so Phase A persistence, Phase B
display, and Phase C scheduler/email all agree.

Locked 2026-05-03 (revised same day):
  Tax email triggers:  Untaxed, SORN, Not Taxed for on Road Use
  MOT email triggers:  Not valid, No results returned
  Safe (no email):     Taxed, Valid, Could not verify (retry policy handles),
                       No details held by DVLA (mostly MOT-exempt cars under
                         3 years old — would fire on every nearly-new car)
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# Values stored when DVLA itself can't be reached. Not from the DVLA spec —
# this is our internal sentinel. The 24h-before scheduler retries; if it
# stays this way after 3 daily ticks, the vehicle freezes (no more retries
# until the next vehicle activity touches it).
COULD_NOT_VERIFY = "Could not verify"

# Stop hammering DVLA after this many consecutive "Could not verify" results.
RETRY_FREEZE_AT = 3


# DVLA enum values that should fire an alert email to Kristian.
TAX_ALERT_VALUES = frozenset({
    "Untaxed",
    "SORN",
    "Not Taxed for on Road Use",
})

MOT_ALERT_VALUES = frozenset({
    "Not valid",
    "No results returned",
})


def is_tax_alertable(tax_status: Optional[str]) -> bool:
    """True if this taxStatus value should trigger an email."""
    return tax_status in TAX_ALERT_VALUES


def is_mot_alertable(mot_status: Optional[str]) -> bool:
    """True if this motStatus value should trigger an email."""
    return mot_status in MOT_ALERT_VALUES


def should_alert(tax_status: Optional[str], mot_status: Optional[str]) -> bool:
    """True if either field warrants emailing Kristian.

    `None` and "Could not verify" are NEVER alertable — the retry policy
    handles transient/missing data so the daily scheduler doesn't spam
    Kristian on every DVLA blip.
    """
    return is_tax_alertable(tax_status) or is_mot_alertable(mot_status)


# =============================================================================
# DVLA fetch + vehicle refresh — used by the daily scheduler (Phase C).
# Separate from the FastAPI endpoint at /api/vehicles/dvla-lookup so the
# scheduler doesn't need a Request context, and so the retry/freeze logic
# lives in one place.
# =============================================================================

@dataclass
class DvlaFetchResult:
    """Outcome of one call to DVLA's Vehicle Enquiry Service.

    `success=True` means we got a 200 with parseable JSON — `tax_status`
    and `mot_status` reflect DVLA's strings (may still be alertable).
    `success=False` means DVLA was unreachable / 5xx / timeout — the
    caller should treat this as "Could not verify" and increment retry.
    `not_found=True` is the special case where DVLA explicitly said the
    vehicle doesn't exist (404). Caller should NOT increment retry —
    further retries won't help, the reg is genuinely bad.

    `tax_due_date` / `mot_expiry_date` come from DVLA's `taxDueDate` /
    `motExpiryDate`. Either may be None even on success — DVLA omits
    `motExpiryDate` for MOT-exempt vehicles under 3 years old.
    """
    success: bool
    not_found: bool = False
    tax_status: Optional[str] = None
    mot_status: Optional[str] = None
    tax_due_date: Optional[date] = None
    mot_expiry_date: Optional[date] = None
    http_status: Optional[int] = None
    error: Optional[str] = None


def _parse_iso_date(raw: Optional[str]) -> Optional[date]:
    """DVLA dates come as 'YYYY-MM-DD'. Coerce to date or None."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def fetch_dvla_status(
    registration: str,
    api_key: str,
    *,
    is_production: bool,
    timeout_seconds: float = 10.0,
) -> DvlaFetchResult:
    """Call DVLA's Vehicle Enquiry Service, return tax/MOT status.

    No DB access — pure HTTP wrapper. Caller is responsible for
    persisting the result and applying retry/freeze logic.

    Sync because the only callers (the scheduler and at-creation hook)
    run in sync contexts. The FastAPI endpoint at /api/vehicles/dvla-lookup
    has its own inline async call and is not affected.
    """
    if is_production:
        url = "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"
    else:
        url = "https://uat.driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles"

    try:
        with httpx.Client() as client:
            response = client.post(
                url,
                json={"registrationNumber": registration},
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                timeout=timeout_seconds,
            )
            if response.status_code == 200:
                data = response.json()
                return DvlaFetchResult(
                    success=True,
                    tax_status=data.get("taxStatus"),
                    mot_status=data.get("motStatus"),
                    tax_due_date=_parse_iso_date(data.get("taxDueDate")),
                    mot_expiry_date=_parse_iso_date(data.get("motExpiryDate")),
                    http_status=200,
                )
            if response.status_code == 404:
                return DvlaFetchResult(
                    success=False,
                    not_found=True,
                    http_status=404,
                    error="Vehicle not found",
                )
            return DvlaFetchResult(
                success=False,
                http_status=response.status_code,
                error=f"DVLA returned {response.status_code}",
            )
    except httpx.TimeoutException:
        return DvlaFetchResult(success=False, error="DVLA timeout")
    except Exception as e:  # network/parse/anything-else
        logger.exception("DVLA fetch failed for %s", registration)
        return DvlaFetchResult(success=False, error=str(e))


def refresh_vehicle_dvla(db, vehicle, *, api_key: str, is_production: bool) -> bool:
    """Refresh a vehicle's DVLA compliance state, persist, return True if alertable.

    On DVLA success → write tax_status/mot_status, set dvla_checked_at,
    reset dvla_retry_count to 0.
    On DVLA failure → set both statuses to "Could not verify", increment
    dvla_retry_count. After RETRY_FREEZE_AT consecutive failures the row
    is frozen (no further refresh attempts until something else touches it).
    On DVLA 404 → set both to None (genuine bad reg, retries won't help),
    leave dvla_retry_count alone.

    Returns True if the resulting state should fire a compliance alert
    (per `should_alert`). False otherwise — including all "Could not
    verify" cases (retry policy, not the email path).
    """
    if vehicle.dvla_retry_count is not None and vehicle.dvla_retry_count >= RETRY_FREEZE_AT:
        logger.info(
            "vehicle %s frozen at retry_count=%s, skipping DVLA refresh",
            vehicle.id, vehicle.dvla_retry_count,
        )
        return False

    result = fetch_dvla_status(
        vehicle.registration,
        api_key,
        is_production=is_production,
    )
    now = datetime.now(timezone.utc)

    if result.success:
        vehicle.tax_status = result.tax_status
        vehicle.mot_status = result.mot_status
        vehicle.tax_due_date = result.tax_due_date
        vehicle.mot_expiry_date = result.mot_expiry_date
        vehicle.dvla_checked_at = now
        vehicle.dvla_retry_count = 0
        db.commit()
        return should_alert(result.tax_status, result.mot_status)

    if result.not_found:
        vehicle.tax_status = None
        vehicle.mot_status = None
        vehicle.tax_due_date = None
        vehicle.mot_expiry_date = None
        vehicle.dvla_checked_at = now
        # do NOT increment retry — 404 is permanent for this reg
        db.commit()
        return False

    # Anything else: transient DVLA failure → Could not verify + retry
    vehicle.tax_status = COULD_NOT_VERIFY
    vehicle.mot_status = COULD_NOT_VERIFY
    vehicle.dvla_checked_at = now
    vehicle.dvla_retry_count = (vehicle.dvla_retry_count or 0) + 1
    db.commit()
    return False


def check_and_alert_for_booking(db, booking) -> bool:
    """Fire a compliance alert email for `booking` if its vehicle is alertable.

    Called from the 3 CONFIRMED-transition points (manual confirm, Stripe
    webhook, free-booking path). Uses the vehicle's *existing* tax/MOT
    state — does NOT re-fetch from DVLA. Front-end DVLA lookup at vehicle
    creation already populated the row; this hook just acts on what's
    there.

    Per-booking dedup: skips if `last_compliance_alert_sent_at` is in
    today's UK day window.

    Returns True iff an alert was actually sent (SendGrid 2xx). Staging
    guard inside `send_vehicle_compliance_alert` returns False without
    sending, so this also returns False on staging.
    """
    import pytz
    from email_service import send_vehicle_compliance_alert

    vehicle = booking.vehicle
    if vehicle is None or not should_alert(vehicle.tax_status, vehicle.mot_status):
        return False

    uk_tz = pytz.timezone("Europe/London")
    now_uk = datetime.now(uk_tz)
    today_start_uk = uk_tz.localize(
        datetime.combine(now_uk.date(), datetime.min.time())
    )

    if (
        booking.last_compliance_alert_sent_at is not None
        and booking.last_compliance_alert_sent_at >= today_start_uk
    ):
        return False  # already alerted today

    customer_first = booking.customer_first_name or (
        booking.customer.first_name if booking.customer else ""
    )
    customer_last = booking.customer_last_name or (
        booking.customer.last_name if booking.customer else ""
    )
    sent = send_vehicle_compliance_alert(
        booking_reference=booking.reference,
        customer_name=f"{customer_first} {customer_last}".strip(),
        registration=vehicle.registration,
        dropoff_date=booking.dropoff_date.strftime("%d/%m/%Y"),
        dropoff_time=(
            booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else "—"
        ),
        tax_status=vehicle.tax_status,
        mot_status=vehicle.mot_status,
    )
    if sent:
        booking.last_compliance_alert_sent_at = now_uk
        db.commit()
    return sent


async def check_and_alert_for_booking_async(booking_id: int) -> None:
    """BackgroundTask-friendly wrapper around `check_and_alert_for_booking`.

    Called from CONFIRMED-transition endpoints (Stripe webhook, manual
    mark-paid, free-booking path). Opens its own DB session so the request
    handler's session isn't kept alive across the email round-trip.
    Swallows all exceptions — the customer's payment / confirmation flow
    must not 500 because of a SendGrid hiccup.
    """
    from database import SessionLocal
    from db_models import Booking

    try:
        db = SessionLocal()
        try:
            booking = db.query(Booking).filter(Booking.id == booking_id).first()
            if booking:
                check_and_alert_for_booking(db, booking)
        finally:
            db.close()
    except Exception:
        logger.exception(
            "compliance alert hook failed for booking %s — swallowing", booking_id
        )
