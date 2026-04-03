"""
SMS service for sending messages via The SMS Works API.

API Documentation: https://api.thesmsworks.co.uk/v1
"""
import os
import re
import uuid
import logging
import httpx
from datetime import datetime
from typing import Optional
import pytz

logger = logging.getLogger(__name__)

# SMS Works configuration
# JWT token is pre-generated in the SMS Works dashboard (API Key tab)
# Tokens do not expire but should be treated like passwords
SMS_JWT_TOKEN = os.getenv("SMS_JWT_TOKEN", "").strip()
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "TAGParking")
SMS_ENABLED = os.getenv("SMS_ENABLED", "false").lower() == "true"

# API base URL
SMS_API_BASE_URL = "https://api.thesmsworks.co.uk/v1"

# UK timezone
UK_TZ = pytz.timezone('Europe/London')

# Template variables available for substitution
TEMPLATE_VARIABLES = {
    "first_name": "Customer first name",
    "last_name": "Customer last name",
    "booking_reference": "Booking reference (e.g., TAG-ABC123)",
    "dropoff_date": "Drop-off date (DD/MM/YYYY)",
    "dropoff_time": "Drop-off time (HH:MM)",
    "pickup_date": "Pick-up date (DD/MM/YYYY)",
    "pickup_time": "Pick-up time (HH:MM)",
    "destination": "Flight destination",
    "vehicle_reg": "Vehicle registration",
    "total_price": "Total price paid",
    "days": "Number of parking days",
    "google_review_link": "Google Review link",
}

# Static links
GOOGLE_REVIEW_LINK = "https://g.page/r/CbA2WXPNrM9fEAE/review"


def is_sms_enabled() -> bool:
    """Check if SMS sending is enabled (JWT token configured)."""
    return SMS_ENABLED and bool(SMS_JWT_TOKEN)


def get_jwt_token() -> Optional[str]:
    """
    Get the pre-generated JWT token from environment.

    SMS Works tokens are generated in the dashboard (API Key tab),
    not via API login. Tokens do not expire.
    """
    if not SMS_JWT_TOKEN:
        logger.warning("SMS JWT token not configured")
        return None

    return SMS_JWT_TOKEN


def format_phone_number(phone: str) -> str:
    """
    Format UK phone number to international format (44XXXXXXXXXX).

    Handles:
    - 07... -> 447...
    - +447... -> 447...
    - +44 7... -> 447... (with spaces)
    - 00447... -> 447...
    - 447... -> 447... (already international)
    - 08... -> 448... (UK non-geographic)
    """
    # Remove all non-digit characters (spaces, dashes, +, etc.)
    digits = re.sub(r'\D', '', phone)

    # Remove leading 00 (international dialing prefix)
    if digits.startswith('00'):
        digits = digits[2:]

    # Convert UK national format to international
    if digits.startswith('0') and len(digits) == 11:
        # UK national format: 0XXXXXXXXXX -> 44XXXXXXXXXX
        digits = '44' + digits[1:]
    elif digits.startswith('7') and len(digits) == 10:
        # Missing leading 0: 7XXXXXXXXX -> 447XXXXXXXXX
        digits = '44' + digits
    # Already starts with 44 - keep as is

    return digits


def validate_phone_number(phone: str) -> bool:
    """Validate that phone number is a valid UK number (mobile or landline)."""
    formatted = format_phone_number(phone)
    # UK number: 44XXXXXXXXXX (12 digits starting with 44)
    # Accept any UK number format, let the SMS provider validate mobile
    return len(formatted) >= 11 and len(formatted) <= 13 and formatted.startswith('44')


def render_template(template_content: str, variables: dict) -> str:
    """
    Render template by substituting {{VARIABLE}} placeholders.

    Args:
        template_content: Template string with {{VARIABLE}} placeholders
        variables: Dict mapping variable names to values

    Returns:
        Rendered template string
    """
    result = template_content

    for var_name, var_value in variables.items():
        # Handle both {{var}} and {{ var }} formats
        patterns = [
            f"{{{{{var_name}}}}}",
            f"{{{{ {var_name} }}}}",
        ]
        for pattern in patterns:
            result = result.replace(pattern, str(var_value) if var_value else "")

    return result


def get_booking_variables(booking) -> dict:
    """
    Extract template variables from a booking object.

    Args:
        booking: Booking SQLAlchemy model instance

    Returns:
        Dict of variable name -> value
    """
    # Get customer name (use snapshot if available, fallback to customer object)
    first_name = booking.customer_first_name or (booking.customer.first_name if booking.customer else "")
    last_name = booking.customer_last_name or (booking.customer.last_name if booking.customer else "")

    # Calculate days
    days = 0
    if booking.dropoff_date and booking.pickup_date:
        days = (booking.pickup_date - booking.dropoff_date).days

    # Get total price from payment
    total_price = ""
    if booking.payment and booking.payment.amount_pence:
        total_price = f"£{booking.payment.amount_pence / 100:.2f}"

    # Format times
    dropoff_time = ""
    if booking.dropoff_time:
        dropoff_time = booking.dropoff_time.strftime("%H:%M")

    pickup_time = ""
    if booking.pickup_time:
        pickup_time = booking.pickup_time.strftime("%H:%M")

    return {
        "first_name": first_name,
        "last_name": last_name,
        "booking_reference": booking.reference or "",
        "dropoff_date": booking.dropoff_date.strftime("%d/%m/%Y") if booking.dropoff_date else "",
        "dropoff_time": dropoff_time,
        "pickup_date": booking.pickup_date.strftime("%d/%m/%Y") if booking.pickup_date else "",
        "pickup_time": pickup_time,
        "destination": booking.dropoff_destination or "",
        "vehicle_reg": booking.vehicle.registration if booking.vehicle else "",
        "total_price": total_price,
        "days": str(days),
        "google_review_link": GOOGLE_REVIEW_LINK,
    }


async def send_sms(
    phone: str,
    content: str,
    tag: str = None,
    booking_id: int = None,
    customer_id: int = None,
    template_id: int = None,
    sent_by: int = None,
    db_session=None
) -> dict:
    """
    Send a single SMS message.

    Args:
        phone: Recipient phone number
        content: Message content (max 160 chars for single SMS)
        tag: Optional tag for tracking
        booking_id: Optional booking ID to link message to
        customer_id: Optional customer ID to link message to
        template_id: Optional template ID if using a template
        sent_by: Optional user ID who sent the message
        db_session: Optional database session for logging

    Returns:
        Dict with success status and message details
    """
    from db_models import SMSMessage, SMSDirection, SMSStatus

    if not is_sms_enabled():
        logger.warning("SMS sending disabled - message not sent")
        return {"success": False, "error": "SMS sending is disabled"}

    # Validate phone number
    if not validate_phone_number(phone):
        return {"success": False, "error": f"Invalid UK phone number: {phone}"}

    formatted_phone = format_phone_number(phone)

    # Get JWT token
    token = get_jwt_token()
    if not token:
        return {"success": False, "error": "Failed to authenticate with SMS provider"}

    # Create SMS message record if db session provided
    sms_record = None
    if db_session:
        sms_record = SMSMessage(
            phone_number=formatted_phone,
            booking_id=booking_id,
            customer_id=customer_id,
            template_id=template_id,
            direction=SMSDirection.OUTBOUND,
            content=content,
            status=SMSStatus.PENDING,
            sent_by=sent_by,
        )
        db_session.add(sms_record)
        db_session.flush()  # Get ID before API call

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SMS_API_BASE_URL}/message/send",
                headers={
                    "Authorization": f"JWT {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "sender": SMS_SENDER_ID,
                    "destination": formatted_phone,
                    "content": content,
                    "tag": tag or "tag-parking",
                }
            )

            if response.status_code in (200, 201):
                data = response.json()
                message_id = data.get("messageid")

                logger.info(f"SMS sent successfully to {formatted_phone}: {message_id}")

                # Update record
                if sms_record:
                    sms_record.provider_message_id = message_id
                    sms_record.status = SMSStatus.SENT
                    db_session.commit()

                return {
                    "success": True,
                    "message_id": message_id,
                    "phone": formatted_phone,
                    "sms_record_id": sms_record.id if sms_record else None,
                }
            else:
                error_msg = f"SMS API error: {response.status_code} - {response.text}"
                logger.error(error_msg)

                if sms_record:
                    sms_record.status = SMSStatus.FAILED
                    sms_record.status_detail = error_msg[:255]
                    db_session.commit()

                return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Error sending SMS: {str(e)}"
        logger.error(error_msg)

        if sms_record:
            sms_record.status = SMSStatus.FAILED
            sms_record.status_detail = error_msg[:255]
            db_session.commit()

        return {"success": False, "error": error_msg}


async def send_bulk_sms(
    messages: list,
    db_session=None,
    sent_by: int = None
) -> dict:
    """
    Send bulk SMS messages.

    Args:
        messages: List of dicts with 'phone', 'content', and optional 'booking_id', 'customer_id'
        db_session: Database session for logging
        sent_by: User ID who initiated the bulk send

    Returns:
        Dict with success counts and details
    """
    if not is_sms_enabled():
        return {"success": False, "error": "SMS sending is disabled", "sent": 0, "failed": 0}

    batch_id = str(uuid.uuid4())[:8]
    results = {
        "success": True,
        "batch_id": batch_id,
        "sent": 0,
        "failed": 0,
        "details": [],
    }

    for msg in messages:
        phone = msg.get("phone")
        content = msg.get("content")
        booking_id = msg.get("booking_id")
        customer_id = msg.get("customer_id")
        template_id = msg.get("template_id")

        result = await send_sms(
            phone=phone,
            content=content,
            tag=f"bulk-{batch_id}",
            booking_id=booking_id,
            customer_id=customer_id,
            template_id=template_id,
            sent_by=sent_by,
            db_session=db_session,
        )

        if result.get("success"):
            results["sent"] += 1
        else:
            results["failed"] += 1

        results["details"].append({
            "phone": phone,
            "success": result.get("success"),
            "error": result.get("error"),
            "message_id": result.get("message_id"),
        })

    if results["failed"] > 0 and results["sent"] == 0:
        results["success"] = False

    return results


async def send_booking_confirmation_sms(booking, db_session) -> bool:
    """
    Send booking confirmation SMS using the automated template.

    Called from email_service.py when confirmation email is sent.

    Args:
        booking: Booking model instance
        db_session: Database session

    Returns:
        True if sent successfully, False otherwise
    """
    from db_models import SMSTemplate

    if not is_sms_enabled():
        logger.info("SMS disabled - skipping booking confirmation SMS")
        return False

    # Get customer phone
    if not booking.customer or not booking.customer.phone:
        logger.warning(f"No phone number for booking {booking.reference}")
        return False

    # Get the automated template
    template = db_session.query(SMSTemplate).filter(
        SMSTemplate.trigger_event == "booking_confirmed",
        SMSTemplate.is_active == True,
        SMSTemplate.is_automated == True,
    ).first()

    if not template:
        logger.warning("No active booking_confirmed SMS template found")
        return False

    # Render template with booking variables
    variables = get_booking_variables(booking)
    content = render_template(template.content, variables)

    # Send SMS
    result = await send_sms(
        phone=booking.customer.phone,
        content=content,
        tag="booking-confirmation",
        booking_id=booking.id,
        customer_id=booking.customer.id,
        template_id=template.id,
        db_session=db_session,
    )

    return result.get("success", False)


async def send_reminder_2day_sms(booking, db_session) -> bool:
    """
    Send 2-day reminder SMS using the automated template.

    Called from email_service.py when 2-day reminder email is sent.

    Args:
        booking: Booking model instance
        db_session: Database session

    Returns:
        True if sent successfully, False otherwise
    """
    from db_models import SMSTemplate

    if not is_sms_enabled():
        logger.info("SMS disabled - skipping 2-day reminder SMS")
        return False

    # Get customer phone
    if not booking.customer or not booking.customer.phone:
        logger.warning(f"No phone number for booking {booking.reference}")
        return False

    # Get the automated template
    template = db_session.query(SMSTemplate).filter(
        SMSTemplate.trigger_event == "reminder_2day",
        SMSTemplate.is_active == True,
        SMSTemplate.is_automated == True,
    ).first()

    if not template:
        logger.warning("No active reminder_2day SMS template found")
        return False

    # Render template with booking variables
    variables = get_booking_variables(booking)
    content = render_template(template.content, variables)

    # Send SMS
    result = await send_sms(
        phone=booking.customer.phone,
        content=content,
        tag="reminder-2day",
        booking_id=booking.id,
        customer_id=booking.customer.id,
        template_id=template.id,
        db_session=db_session,
    )

    return result.get("success", False)


async def send_thank_you_sms(booking, db_session) -> bool:
    """
    Send thank you SMS using the automated template.

    Called from email_scheduler.py when thank you email is sent.

    Args:
        booking: Booking model instance
        db_session: Database session

    Returns:
        True if sent successfully, False otherwise
    """
    from db_models import SMSTemplate

    if not is_sms_enabled():
        logger.info("SMS disabled - skipping thank you SMS")
        return False

    # Get customer phone
    if not booking.customer or not booking.customer.phone:
        logger.warning(f"No phone number for booking {booking.reference}")
        return False

    # Get the automated template
    template = db_session.query(SMSTemplate).filter(
        SMSTemplate.trigger_event == "thank_you",
        SMSTemplate.is_active == True,
        SMSTemplate.is_automated == True,
    ).first()

    if not template:
        logger.warning("No active thank_you SMS template found")
        return False

    # Render template with booking variables
    variables = get_booking_variables(booking)
    content = render_template(template.content, variables)

    # Send SMS
    result = await send_sms(
        phone=booking.customer.phone,
        content=content,
        tag="thank-you",
        booking_id=booking.id,
        customer_id=booking.customer.id,
        template_id=template.id,
        db_session=db_session,
    )

    return result.get("success", False)


def handle_delivery_report(payload: dict, db_session) -> bool:
    """
    Handle delivery report webhook from SMS Works.

    Args:
        payload: Webhook payload from SMS Works
        db_session: Database session

    Returns:
        True if processed successfully
    """
    from db_models import SMSMessage, SMSStatus

    message_id = payload.get("messageid")
    status = payload.get("status", "").lower()

    if not message_id:
        logger.warning("Delivery report missing message ID")
        return False

    # Find the message record
    sms_record = db_session.query(SMSMessage).filter(
        SMSMessage.provider_message_id == message_id
    ).first()

    if not sms_record:
        logger.warning(f"SMS record not found for message ID: {message_id}")
        return False

    # Map SMS Works status to our status
    status_map = {
        "delivered": SMSStatus.DELIVERED,
        "sent": SMSStatus.SENT,
        "failed": SMSStatus.FAILED,
        "rejected": SMSStatus.FAILED,
        "expired": SMSStatus.FAILED,
    }

    new_status = status_map.get(status)
    if new_status:
        sms_record.status = new_status
        if new_status == SMSStatus.DELIVERED:
            sms_record.delivered_at = datetime.now(UK_TZ)
        elif new_status == SMSStatus.FAILED:
            sms_record.status_detail = payload.get("failurereason", "")[:255]

        db_session.commit()
        logger.info(f"Updated SMS {message_id} status to {new_status.value}")
        return True

    return False


async def check_message_status(provider_message_id: str) -> Optional[dict]:
    """
    Check message status from SMS Works API.

    Args:
        provider_message_id: The message ID from SMS Works

    Returns:
        Dict with status info or None if failed
    """
    if not is_sms_enabled():
        return None

    token = get_jwt_token()
    if not token:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SMS_API_BASE_URL}/messages/{provider_message_id}",
                headers={
                    "Authorization": f"JWT {token}",
                },
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get message status: {response.status_code}")
                return None

    except Exception as e:
        logger.error(f"Error checking message status: {str(e)}")
        return None


async def refresh_message_statuses(db_session) -> dict:
    """
    Refresh status of all SENT messages from SMS Works API.

    Returns:
        Dict with counts of updated messages
    """
    from db_models import SMSMessage, SMSStatus, SMSDirection

    if not is_sms_enabled():
        return {"success": False, "error": "SMS disabled"}

    # Get all outbound messages with SENT status
    pending_messages = db_session.query(SMSMessage).filter(
        SMSMessage.direction == SMSDirection.OUTBOUND,
        SMSMessage.status == SMSStatus.SENT,
        SMSMessage.provider_message_id != None,
    ).all()

    updated = 0
    failed = 0

    for msg in pending_messages:
        result = await check_message_status(msg.provider_message_id)
        if result:
            status = result.get("status", "").lower()
            status_map = {
                "delivered": SMSStatus.DELIVERED,
                "sent": SMSStatus.SENT,
                "failed": SMSStatus.FAILED,
                "rejected": SMSStatus.FAILED,
                "expired": SMSStatus.FAILED,
                "undeliverable": SMSStatus.FAILED,
            }

            new_status = status_map.get(status)
            if new_status and new_status != msg.status:
                msg.status = new_status
                if new_status == SMSStatus.DELIVERED:
                    msg.delivered_at = datetime.now(UK_TZ)
                elif new_status == SMSStatus.FAILED:
                    failure = result.get("failurereason", {})
                    if isinstance(failure, dict):
                        msg.status_detail = failure.get("details", "")[:255]
                    else:
                        msg.status_detail = str(failure)[:255]
                updated += 1
            else:
                # Status unchanged
                pass
        else:
            failed += 1

    db_session.commit()

    return {"success": True, "updated": updated, "failed": failed, "total": len(pending_messages)}


def handle_incoming_sms(payload: dict, db_session) -> bool:
    """
    Handle incoming SMS webhook from SMS Works.

    Args:
        payload: Webhook payload from SMS Works
        db_session: Database session

    Returns:
        True if processed successfully
    """
    from db_models import SMSMessage, SMSDirection, SMSStatus, Customer

    # SMS Works uses "from" field, but "sender" as fallback for compatibility
    sender = payload.get("from") or payload.get("sender")
    content = payload.get("content", "")
    message_id = payload.get("messageid")

    if not sender:
        logger.warning("Incoming SMS missing sender")
        return False

    # Format phone number
    formatted_phone = format_phone_number(sender)

    # Try to find customer by phone
    customer = db_session.query(Customer).filter(
        Customer.phone.ilike(f"%{formatted_phone[-10:]}%")
    ).first()

    # Create inbound message record
    sms_record = SMSMessage(
        phone_number=formatted_phone,
        customer_id=customer.id if customer else None,
        direction=SMSDirection.INBOUND,
        content=content,
        provider_message_id=message_id,
        status=SMSStatus.DELIVERED,
        delivered_at=datetime.now(UK_TZ),
    )

    db_session.add(sms_record)
    db_session.commit()

    logger.info(f"Received inbound SMS from {formatted_phone}: {content[:50]}...")
    return True


def get_template_variables_list() -> list:
    """Get list of available template variables with descriptions."""
    return [
        {"name": name, "description": desc}
        for name, desc in TEMPLATE_VARIABLES.items()
    ]
