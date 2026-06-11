"""
Email service for sending marketing emails via SendGrid.
"""
import os
import logging
import secrets
import string
from pathlib import Path
from typing import Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)

# Get the directory where this file is located
EMAIL_TEMPLATES_DIR = Path(__file__).parent / "email_templates"

# SendGrid configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@tagparking.co.uk")
FROM_NAME = os.getenv("FROM_NAME", "TAG Parking")

# Founder email configuration (for personal follow-up emails)
FOUNDER_EMAIL = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")
FOUNDER_NAME = os.getenv("FOUNDER_NAME", "Kristian")


def is_email_enabled() -> bool:
    """Check if email sending is enabled (API key is configured)."""
    return bool(SENDGRID_API_KEY)


def is_staging_email_guard_active() -> bool:
    """Staging must never deliver real email (2026-06-11 incident: E2E runs
    pushed SendGrid sends to example.com addresses and CC'd the founder's
    real inbox). Guarded at the base senders so every caller — current and
    future — inherits it. Same env contract as
    db_service.should_exclude_staging_e2e_capacity_bookings().
    """
    return os.environ.get("ENVIRONMENT", "").strip().lower() == "staging"


def generate_promo_code() -> str:
    """
    Generate a unique promo code in format TAG-XXXX-XXXX.

    Uses cryptographically secure random characters for uniqueness.
    Example: TAG-A3K9-M2P7
    """
    chars = string.ascii_uppercase + string.digits
    # Remove confusing characters (0, O, I, 1, L)
    chars = chars.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')

    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(chars) for _ in range(4))

    return f"TAG-{part1}-{part2}"


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    Send an email via SendGrid.

    Returns True if sent successfully, False otherwise.
    """
    print(f"[EMAIL] send_email called for: {to_email}, subject: {subject}")
    if is_staging_email_guard_active():
        # Return True (not False) so transactional flows mark the email as
        # handled instead of retry-looping against a send that will never
        # happen in staging.
        print(f"[EMAIL] staging guard active — suppressed send to {to_email}")
        logger.info(
            "[staging] would send email to %s (subject=%s) — staging guard active",
            to_email, subject,
        )
        return True
    if not SENDGRID_API_KEY:
        print("[EMAIL] ERROR: SendGrid API key not configured!")
        logger.warning("SendGrid API key not configured - email not sent")
        return False
    print(f"[EMAIL] SendGrid API key is configured (length: {len(SENDGRID_API_KEY)})")

    try:
        message = Mail(
            from_email=Email(FROM_EMAIL, FROM_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        print(f"[EMAIL] Sending via SendGrid...")
        response = sg.send(message)
        print(f"[EMAIL] SendGrid response status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"[EMAIL] Email sent successfully to {to_email}")
            logger.info(f"Email sent successfully to {to_email}")
            return True
        else:
            print(f"[EMAIL] SendGrid returned non-success status: {response.status_code}")
            logger.error(f"Failed to send email to {to_email}: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Exception sending email: {str(e)}")
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        return False


def send_welcome_email(first_name: str, email: str, unsubscribe_token: str = None) -> bool:
    """Send welcome email to new subscriber using the HTML template."""
    subject = "Thanks for signing up"

    # Build unsubscribe URL
    api_base_url = os.getenv("API_BASE_URL", "https://tagparkingbohgithubio-production.up.railway.app")
    if unsubscribe_token:
        unsubscribe_url = f"{api_base_url}/api/marketing/unsubscribe/{unsubscribe_token}"
    else:
        # Fallback - shouldn't happen but just in case
        unsubscribe_url = "https://tagparking.co.uk"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "welcome_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{UNSUBSCRIBE_URL}}", unsubscribe_url)
    except FileNotFoundError:
        logger.error(f"Welcome email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading welcome email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_promo_code_email(first_name: str, email: str, promo_code: str = "TAG10") -> bool:
    """Send 10% off promo code email to subscriber."""
    subject = f"{first_name}, here's a 10% off promo code"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "promo_10_percent_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{PROMO_CODE}}", promo_code)
    except FileNotFoundError:
        logger.error(f"10% promo email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading 10% promo email template: {e}")
        return False

    return send_email(email, subject, html_content)


def _send_template_email(email: str, subject: str, template_name: str, replacements: dict) -> bool:
    template_path = EMAIL_TEMPLATES_DIR / template_name
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        for key, value in replacements.items():
            html_content = html_content.replace(f"{{{{{key}}}}}", str(value or ""))
    except FileNotFoundError:
        logger.error(f"Email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading email template {template_name}: {e}")
        return False
    return send_email(email, subject, html_content)


def _render_template(template_name: str, replacements: dict) -> Optional[str]:
    template_path = EMAIL_TEMPLATES_DIR / template_name
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        for key, value in replacements.items():
            html_content = html_content.replace(f"{{{{{key}}}}}", str(value or ""))
        return html_content
    except FileNotFoundError:
        logger.error(f"Email template not found at {template_path}")
        return None
    except Exception as e:
        logger.error(f"Error loading email template {template_name}: {e}")
        return None


def _referral_action_buttons(yes_url: str, no_url: str) -> str:
    return f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tr>
        <td align="left" style="padding: 20px 0 8px;">
          <a href="{yes_url}" style="display:inline-block; padding:12px 18px; background:#181818; color:#ccff00; text-decoration:none; border-radius:6px; font-weight:bold;">Yes, send my code</a>
          <a href="{no_url}" style="display:inline-block; padding:12px 18px; margin-left:8px; background:#ffffff; color:#181818; text-decoration:none; border-radius:6px; font-weight:bold;">No thanks</a>
        </td>
      </tr>
    </table>
    """


def _referral_code_section(label: str, code: str) -> str:
    return f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tr>
        <td align="center" style="padding: 20px 0;">
          <div style="background-color:#181818; border-radius:8px; padding:20px; display:inline-block;">
            <p style="margin:0 0 10px 0; font-size:14px; color:#ccff00;">{label}</p>
            <p style="margin:0; font-size:28px; font-weight:bold; color:#ffffff; letter-spacing:2px;">{code}</p>
          </div>
        </td>
      </tr>
    </table>
    """


def _remove_unsubscribe_block(html_content: str) -> str:
    start_marker = "<!-- Unsubscribe -->"
    end_marker = "<!-- Copyright -->"
    start = html_content.find(start_marker)
    end = html_content.find(end_marker)
    if start == -1 or end == -1 or end <= start:
        return html_content
    return html_content[:start] + html_content[end:]


def _send_referral_email(
    email: str,
    first_name: str,
    subject: str,
    template_name: str,
    replacements: dict,
    promo_code_section: str = "",
) -> bool:
    message = _render_template(template_name, replacements)
    if message is None:
        return False

    founder_name = os.getenv("FOUNDER_NAME", "Kristian")
    api_base_url = os.getenv("API_BASE_URL", "https://tagparkingbohgithubio-production.up.railway.app")
    html_content = _render_template("marketing_campaign_email.html", {
        "SUBJECT": subject,
        "FIRST_NAME": first_name or "there",
        "MESSAGE": message,
        "PROMO_CODE_SECTION": promo_code_section,
        "FOUNDER_NAME": founder_name,
        "UNSUBSCRIBE_URL": f"{api_base_url}/api/marketing/unsubscribe",
        "PREVIEW_TEXT": subject[:100],
    })
    if html_content is None:
        return False
    html_content = _remove_unsubscribe_block(html_content)
    return send_email(email, subject, html_content)


def send_referral_invite_email(
    first_name: str,
    email: str,
    yes_url: str,
    no_url: str,
    intro_line: str = "Thanks again for parking with Tag. Would you like to join our referral program?",
) -> bool:
    subject = f"{first_name}, join Tag's referral program?"
    return _send_referral_email(email, first_name, subject, "referral_invite_email.html", {
        "INTRO_LINE": intro_line,
        "ACTION_BUTTONS": _referral_action_buttons(yes_url, no_url),
    })


def send_referral_invite_reminder_email(first_name: str, email: str, yes_url: str, no_url: str) -> bool:
    subject = f"{first_name}, still interested in Tag referrals?"
    return _send_referral_email(email, first_name, subject, "referral_invite_reminder_email.html", {
        "ACTION_BUTTONS": _referral_action_buttons(yes_url, no_url),
    })


def send_referral_code_email(first_name: str, email: str, referral_code: str) -> bool:
    subject = f"{first_name}, your Tag referral code is ready"
    return _send_referral_email(
        email,
        first_name,
        subject,
        "referral_code_email.html",
        {},
        promo_code_section=_referral_code_section("Your referral code:", referral_code),
    )


def send_referral_reward_email(first_name: str, email: str, reward_code: str) -> bool:
    subject = f"{first_name}, you earned a Tag referral reward"
    return _send_referral_email(
        email,
        first_name,
        subject,
        "referral_reward_email.html",
        {},
        promo_code_section=_referral_code_section("Your reward code:", reward_code),
    )


def send_login_code_email(email: str, first_name: str, code: str) -> bool:
    """
    Send 6-digit login code to user.

    Args:
        email: User's email address
        first_name: User's first name
        code: 6-digit login code

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = f"Your TAG login code: {code}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <!-- Header -->
            <div style="background: #1a1a2e; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: #D9FF00; margin: 0; font-size: 32px; font-weight: bold;">TAG</h1>
                <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 14px;">Staff Login</p>
            </div>

            <!-- Main Content -->
            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 16px; margin-bottom: 20px;">Hi {first_name},</p>

                <p style="font-size: 16px; margin-bottom: 25px;">
                    Here's your login code. It expires in 10 minutes.
                </p>

                <!-- Code Box -->
                <div style="background: #1a1a2e; padding: 25px; text-align: center; border-radius: 8px; margin-bottom: 25px;">
                    <p style="color: #D9FF00; margin: 0; font-size: 36px; font-weight: bold; letter-spacing: 8px;">{code}</p>
                </div>

                <p style="font-size: 14px; color: #666;">
                    If you didn't request this code, you can safely ignore this email.
                </p>
            </div>

            <!-- Footer -->
            <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
                <p style="margin: 0;">TAG Parking | Bournemouth International Airport</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(email, subject, html_content)


def send_booking_confirmation_email(
    email: str,
    first_name: str,
    booking_reference: str,
    dropoff_date: str,
    dropoff_time: str,
    pickup_date: str,
    pickup_time: str,
    flight_arrival_time: str,
    flight_departure_time: str,
    departure_flight: str,
    return_flight: str,
    vehicle_make: str,
    vehicle_colour: str,
    vehicle_registration: str,
    package_name: str,
    amount_paid: str,
    arrival_date: str = "",
    vehicle_model: str = None,  # Deprecated - DVLA API doesn't provide model
    promo_code: str = None,
    discount_amount: str = None,
    original_amount: str = None,
) -> bool:
    """
    Send booking confirmation email after successful payment using the HTML template.

    Args:
        email: Customer email address
        first_name: Customer first name
        booking_reference: Unique booking reference (e.g., TAG-XXXXXXXX)
        dropoff_date: Formatted drop-off date (e.g., "Saturday, 28 December 2025")
        dropoff_time: Drop-off time (e.g., "10:15")
        pickup_date: Formatted pickup date (e.g., "Saturday, 4 January 2026")
        pickup_time: Pickup time - 30 mins after arrival (e.g., "15:30")
        flight_arrival_time: Flight arrival/landing time (e.g., "15:00")
        departure_flight: Flight details (e.g., "TOM1234 to Tenerife (TFS)")
        return_flight: Return flight details (e.g., "TOM1235 from Tenerife (TFS)")
        vehicle_make: Vehicle make
        vehicle_model: Vehicle model
        vehicle_colour: Vehicle colour
        vehicle_registration: Registration plate
        package_name: Package name (e.g., "1 Week" or "2 Weeks")
        amount_paid: Amount paid (e.g., "£99.00")
        arrival_date: Canonical landing date for the return flight, formatted
            ("Monday, 8 July 2026"). Distinct from pickup_date — for overnight
            arrivals the customer lands the day BEFORE pickup_date. Falls back
            to pickup_date when empty so legacy callers keep working.
        promo_code: Optional promo code used
        discount_amount: Optional discount amount (e.g., "£9.90")

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = f"Booking Confirmed - {booking_reference}"

    # Build discount section if applicable (subtotal + discount rows)
    discount_section = ""
    if promo_code and discount_amount:
        # Show original price as subtotal when available
        subtotal_row = ""
        if original_amount:
            subtotal_row = f"""
<tr>
<td style="padding:10px 0; border-bottom:1px solid #e5e5e5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr>
<td style="font-family: Helvetica, Arial, sans-serif; color:#666666; font-size:16px;">Subtotal</td>
<td align="right" style="font-family: Helvetica, Arial, sans-serif; color:#343434; font-size:16px;">{original_amount}</td>
</tr>
</table>
</td>
</tr>
"""
        discount_section = f"""{subtotal_row}
<tr>
<td style="padding:10px 0; border-bottom:1px solid #e5e5e5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr>
<td style="font-family: Helvetica, Arial, sans-serif; color:#22c55e; font-size:16px;">Promo Code ({promo_code})</td>
<td align="right" style="font-family: Helvetica, Arial, sans-serif; color:#22c55e; font-size:16px;">-{discount_amount}</td>
</tr>
</table>
</td>
</tr>
"""

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "booking_confirmation_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{BOOKING_REFERENCE}}", booking_reference)
        html_content = html_content.replace("{{DROPOFF_DATE}}", dropoff_date)
        html_content = html_content.replace("{{DROPOFF_TIME}}", dropoff_time)
        html_content = html_content.replace("{{PICKUP_DATE}}", pickup_date)
        html_content = html_content.replace("{{PICKUP_TIME}}", pickup_time)
        # Canonical landing date for the return flight. Falls back to
        # pickup_date when not provided so legacy callers continue to render
        # something sensible (the date matches pre-2026-05-20 behaviour for
        # non-overnight arrivals).
        html_content = html_content.replace("{{ARRIVAL_DATE}}", arrival_date or pickup_date)
        html_content = html_content.replace("{{FLIGHT_ARRIVAL_TIME}}", flight_arrival_time)
        html_content = html_content.replace("{{FLIGHT_DEPARTURE_TIME}}", flight_departure_time)
        html_content = html_content.replace("{{DEPARTURE_FLIGHT}}", departure_flight)
        html_content = html_content.replace("{{RETURN_FLIGHT}}", return_flight)
        html_content = html_content.replace("{{VEHICLE_MAKE}}", vehicle_make)
        html_content = html_content.replace("{{VEHICLE_MODEL}}", vehicle_model or "")
        html_content = html_content.replace("{{VEHICLE_COLOUR}}", vehicle_colour)
        html_content = html_content.replace("{{VEHICLE_REGISTRATION}}", vehicle_registration)
        html_content = html_content.replace("{{PACKAGE_NAME}}", package_name)
        html_content = html_content.replace("{{AMOUNT_PAID}}", amount_paid)
        html_content = html_content.replace("{{DISCOUNT_SECTION}}", discount_section)

    except FileNotFoundError:
        logger.error(f"Booking confirmation email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading booking confirmation email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_cancellation_email(
    email: str,
    first_name: str,
    booking_reference: str,
    dropoff_date: str,
) -> bool:
    """
    Send booking cancellation email using the HTML template.

    Args:
        email: Customer email address
        first_name: Customer first name
        booking_reference: Unique booking reference (e.g., TAG-XXXXXXXX)
        dropoff_date: Formatted drop-off date (e.g., "Saturday, 28 December 2025")

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = f"Booking Cancelled - {booking_reference}"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "booking_cancellation_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{BOOKING_REFERENCE}}", booking_reference)
        html_content = html_content.replace("{{DROPOFF_DATE}}", dropoff_date)

    except FileNotFoundError:
        logger.error(f"Booking cancellation email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading booking cancellation email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_refund_email(
    email: str,
    first_name: str,
    booking_reference: str,
    refund_amount: str,
) -> bool:
    """
    Send refund confirmation email using the HTML template.

    Args:
        email: Customer email address
        first_name: Customer first name
        booking_reference: Unique booking reference (e.g., TAG-XXXXXXXX)
        refund_amount: Amount refunded (e.g., "£99.00")

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = f"Refund Processed - {booking_reference}"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "booking_refund_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{BOOKING_REFERENCE}}", booking_reference)
        html_content = html_content.replace("{{REFUND_AMOUNT}}", refund_amount)

    except FileNotFoundError:
        logger.error(f"Booking refund email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading booking refund email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_2_day_reminder_email(
    email: str,
    first_name: str,
    last_name: str,
    booking_reference: str,
    dropoff_date: str,
    dropoff_time: str,
    flight_departure_time: str,
) -> bool:
    """
    Send 2-day reminder email before booking.

    Args:
        email: Customer email address
        first_name: Customer first name
        last_name: Customer last name
        booking_reference: Unique booking reference (e.g., TAG-XXXXXXXX)
        dropoff_date: Formatted drop-off date (e.g., "Friday, 13 February 2026")
        dropoff_time: Agreed meeting/slot time (e.g., "12:10")
        flight_departure_time: Actual flight departure time (e.g., "14:10")

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = f"Where to Meet Us - {booking_reference}"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "2_day_reminder_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{LAST_NAME}}", last_name)
        html_content = html_content.replace("{{BOOKING_REFERENCE}}", booking_reference)
        html_content = html_content.replace("{{DROPOFF_DATE}}", dropoff_date)
        html_content = html_content.replace("{{DROPOFF_TIME}}", dropoff_time)
        html_content = html_content.replace("{{FLIGHT_DEPARTURE_TIME}}", flight_departure_time)

    except FileNotFoundError:
        logger.error(f"2-day reminder email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading 2-day reminder email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_parking_update_email(
    email: str,
    first_name: str,
    booking_reference: str,
    dropoff_date: str,
    dropoff_time: str,
) -> bool:
    """
    Send the one-off parking charges service update before drop-off.

    This is a transactional/service update for an existing booking, so the
    template intentionally does not include a marketing unsubscribe link.
    """
    subject = f"Parking Update - {booking_reference}"
    template_path = EMAIL_TEMPLATES_DIR / "parking_update_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        html_content = html_content.replace("{{FIRST_NAME}}", first_name or "there")
        html_content = html_content.replace("{{BOOKING_REFERENCE}}", booking_reference)
        html_content = html_content.replace("{{DROPOFF_DATE}}", dropoff_date)
        html_content = html_content.replace("{{DROPOFF_TIME}}", dropoff_time)
    except FileNotFoundError:
        logger.error(f"Parking update email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading parking update email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_thank_you_email(
    email: str,
    first_name: str,
) -> bool:
    """
    Send thank you email after booking completion with review invitation.

    Args:
        email: Customer email address
        first_name: Customer first name

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = "Thank You for Choosing TAG Parking"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "thank_you_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)

    except FileNotFoundError:
        logger.error(f"Thank you email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading thank you email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_manual_booking_payment_email(
    email: str,
    first_name: str,
    dropoff_date: str,
    dropoff_time: str,
    pickup_date: str,
    pickup_time: str,
    vehicle_make: str,
    vehicle_colour: str,
    vehicle_registration: str,
    amount: str,
    payment_link: str,
    arrival_date: str = "",
    flight_arrival_time: str = "",
    vehicle_model: str = None,  # Deprecated - DVLA API doesn't provide model
) -> bool:
    """
    Send payment request email for manual bookings.

    Args:
        email: Customer email address
        first_name: Customer first name
        dropoff_date: Formatted drop-off date (e.g., "Saturday, 28 December 2025")
        dropoff_time: Drop-off time (e.g., "10:15")
        pickup_date: Formatted pickup date (e.g., "Saturday, 4 January 2026")
        pickup_time: Pickup time (e.g., "15:20")
        vehicle_make: Vehicle make
        vehicle_model: Vehicle model
        vehicle_colour: Vehicle colour
        vehicle_registration: Registration plate
        amount: Amount to pay (e.g., "£99.00")
        payment_link: Stripe payment link URL
        arrival_date: Formatted canonical landing date for the return flight
            ("Monday, 8 July 2026"). Falls back to pickup_date when empty so
            legacy callers continue rendering — date matches pre-2026-05-20
            behaviour for non-overnight arrivals.
        flight_arrival_time: Landing time HH:MM. Falls back to pickup_time
            when empty (same legacy-caller safety net).

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = "Complete Your TAG Parking Booking"

    # Load the HTML template
    template_path = EMAIL_TEMPLATES_DIR / "manual_booking_payment_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{DROPOFF_DATE}}", dropoff_date)
        html_content = html_content.replace("{{DROPOFF_TIME}}", dropoff_time)
        html_content = html_content.replace("{{PICKUP_DATE}}", pickup_date)
        html_content = html_content.replace("{{PICKUP_TIME}}", pickup_time)
        html_content = html_content.replace("{{ARRIVAL_DATE}}", arrival_date or pickup_date)
        html_content = html_content.replace("{{FLIGHT_ARRIVAL_TIME}}", flight_arrival_time or pickup_time)
        html_content = html_content.replace("{{VEHICLE_MAKE}}", vehicle_make)
        html_content = html_content.replace("{{VEHICLE_MODEL}}", vehicle_model or "")
        html_content = html_content.replace("{{VEHICLE_COLOUR}}", vehicle_colour)
        html_content = html_content.replace("{{VEHICLE_REGISTRATION}}", vehicle_registration)
        html_content = html_content.replace("{{AMOUNT}}", amount)
        html_content = html_content.replace("{{PAYMENT_LINK}}", payment_link)

    except FileNotFoundError:
        logger.error(f"Manual booking payment email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading manual booking payment email template: {e}")
        return False

    return send_email(email, subject, html_content)


def send_founder_thank_you_email(
    email: str,
    first_name: str,
    promo_code: str,
) -> bool:
    """
    Send personal thank you email from founder to marketing subscribers with promo code.

    This email is styled as a personal message from Kristian (founder).
    CC'd to founder's email so they can see responses.

    Args:
        email: Subscriber email address
        first_name: Subscriber first name
        promo_code: Unique promo code for 10% off

    Returns:
        True if sent successfully, False otherwise.
    """
    from sendgrid.helpers.mail import Cc

    subject = os.getenv("FOUNDER_PROMO_EMAIL_SUBJECT", "A personal thank you from me")
    founder_name = os.getenv("FOUNDER_NAME", "Kristian")
    founder_email = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")

    # Load template from file
    template_path = EMAIL_TEMPLATES_DIR / "founder_promo_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{PROMO_CODE}}", promo_code)
        html_content = html_content.replace("{{FOUNDER_NAME}}", founder_name)
    except FileNotFoundError:
        logger.error(f"Founder email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading founder email template: {e}")
        return False

    print(f"[EMAIL] send_founder_thank_you_email called for: {email}, subject: {subject}")
    if is_staging_email_guard_active():
        print(f"[EMAIL] staging guard active — suppressed founder thank-you to {email}")
        logger.info("[staging] would send founder thank-you to %s — staging guard active", email)
        return True
    if not SENDGRID_API_KEY:
        print("[EMAIL] ERROR: SendGrid API key not configured!")
        logger.warning("SendGrid API key not configured - email not sent")
        return False

    try:
        message = Mail(
            from_email=Email(founder_email, founder_name),  # From founder's email
            to_emails=To(email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        print(f"[EMAIL] Sending founder thank you email via SendGrid (CC: {founder_email})...")
        response = sg.send(message)
        print(f"[EMAIL] SendGrid response status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"[EMAIL] Founder thank you email sent successfully to {email}")
            logger.info(f"Founder thank you email sent to {email} (CC: {founder_email})")
            return True
        else:
            print(f"[EMAIL] SendGrid returned non-success status: {response.status_code}")
            logger.error(f"Failed to send founder thank you email to {email}: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Exception sending founder thank you email: {str(e)}")
        logger.error(f"Error sending founder thank you email to {email}: {str(e)}")
        return False


def send_promo_10_reminder_email(
    email: str,
    first_name: str,
    promo_code: str,
) -> bool:
    """
    Send reminder email to subscribers who haven't used their 10% promo code.

    Args:
        email: Subscriber email address
        first_name: Subscriber first name
        promo_code: Their existing 10% promo code

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = os.getenv("FOUNDER_10OFF_REMINDER_EMAIL_SUBJECT", "Don't miss your 10% discount!")
    founder_name = os.getenv("FOUNDER_NAME", "Kristian")
    founder_email = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")

    # Load template from file
    template_path = EMAIL_TEMPLATES_DIR / "promo_10_reminder_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{PROMO_CODE}}", promo_code)
    except FileNotFoundError:
        logger.error(f"Promo 10 reminder email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading promo 10 reminder email template: {e}")
        return False

    print(f"[EMAIL] send_promo_10_reminder_email called for: {email}, subject: {subject}")
    if is_staging_email_guard_active():
        print(f"[EMAIL] staging guard active — suppressed promo-10 reminder to {email}")
        logger.info("[staging] would send promo-10 reminder to %s — staging guard active", email)
        return True
    if not SENDGRID_API_KEY:
        print("[EMAIL] ERROR: SendGrid API key not configured!")
        logger.warning("SendGrid API key not configured - email not sent")
        return False

    try:
        message = Mail(
            from_email=Email(founder_email, founder_name),
            to_emails=To(email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        print(f"[EMAIL] Sending promo 10 reminder email via SendGrid...")
        response = sg.send(message)
        print(f"[EMAIL] SendGrid response status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"[EMAIL] Promo 10 reminder email sent successfully to {email}")
            logger.info(f"Promo 10 reminder email sent to {email}")
            return True
        else:
            print(f"[EMAIL] SendGrid returned non-success status: {response.status_code}")
            logger.error(f"Failed to send promo 10 reminder email to {email}: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Exception sending promo 10 reminder email: {str(e)}")
        logger.error(f"Error sending promo 10 reminder email to {email}: {str(e)}")
        return False


def send_promo_free_reminder_email(
    email: str,
    first_name: str,
    promo_code: str,
) -> bool:
    """
    Send reminder email to subscribers who haven't used their FREE parking promo code.

    Args:
        email: Subscriber email address
        first_name: Subscriber first name
        promo_code: Their existing FREE parking promo code

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = os.getenv("FOUNDER_FREE_REMINDER_EMAIL_SUBJECT", "Your free week of parking is still waiting for you!")
    founder_name = os.getenv("FOUNDER_NAME", "Kristian")
    founder_email = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")

    # Load template from file
    template_path = EMAIL_TEMPLATES_DIR / "promo_free_reminder_email.html"
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Replace placeholders
        html_content = html_content.replace("{{FIRST_NAME}}", first_name)
        html_content = html_content.replace("{{PROMO_CODE}}", promo_code)
    except FileNotFoundError:
        logger.error(f"Promo free reminder email template not found at {template_path}")
        return False
    except Exception as e:
        logger.error(f"Error loading promo free reminder email template: {e}")
        return False

    print(f"[EMAIL] send_promo_free_reminder_email called for: {email}, subject: {subject}")
    if is_staging_email_guard_active():
        print(f"[EMAIL] staging guard active — suppressed promo-free reminder to {email}")
        logger.info("[staging] would send promo-free reminder to %s — staging guard active", email)
        return True
    if not SENDGRID_API_KEY:
        print("[EMAIL] ERROR: SendGrid API key not configured!")
        logger.warning("SendGrid API key not configured - email not sent")
        return False

    try:
        message = Mail(
            from_email=Email(founder_email, founder_name),
            to_emails=To(email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        print(f"[EMAIL] Sending promo free reminder email via SendGrid...")
        response = sg.send(message)
        print(f"[EMAIL] SendGrid response status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"[EMAIL] Promo free reminder email sent successfully to {email}")
            logger.info(f"Promo free reminder email sent to {email}")
            return True
        else:
            print(f"[EMAIL] SendGrid returned non-success status: {response.status_code}")
            logger.error(f"Failed to send promo free reminder email to {email}: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Exception sending promo free reminder email: {str(e)}")
        logger.error(f"Error sending promo free reminder email to {email}: {str(e)}")
        return False


def send_founder_followup_email(
    email: str,
    first_name: str,
) -> bool:
    """
    Send personal follow-up email from founder to abandoned cart customers.

    This email is styled as a personal message, not a marketing template.
    CC'd to founder's email for legitimacy and tracking.

    Args:
        email: Customer email address
        first_name: Customer first name

    Returns:
        True if sent successfully, False otherwise.
    """
    from sendgrid.helpers.mail import Cc

    subject = os.getenv("FOUNDER_EMAIL_SUBJECT", "Quick question about your booking")
    founder_name = os.getenv("FOUNDER_NAME", "Kristian")
    founder_email = os.getenv("FOUNDER_EMAIL", "kristian@tagparking.co.uk")

    # Load template from file
    template_path = os.path.join(os.path.dirname(__file__), "email_templates", "founder_followup_email.html")
    with open(template_path, "r") as f:
        html_content = f.read()

    # Replace placeholders
    html_content = html_content.replace("{{first_name}}", first_name)
    html_content = html_content.replace("{{founder_name}}", founder_name)

    print(f"[EMAIL] send_founder_followup_email called for: {email}, subject: {subject}")
    if is_staging_email_guard_active():
        # Suppress in staging — these CC the founder's real inbox.
        print(f"[EMAIL] staging guard active — suppressed founder followup to {email}")
        logger.info(
            "[staging] would send founder followup to %s (CC %s) — staging guard active",
            email, founder_email,
        )
        return True
    if not SENDGRID_API_KEY:
        print("[EMAIL] ERROR: SendGrid API key not configured!")
        logger.warning("SendGrid API key not configured - email not sent")
        return False

    try:
        message = Mail(
            from_email=Email(founder_email, founder_name),  # From founder's email
            to_emails=To(email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        print(f"[EMAIL] Sending founder followup via SendGrid (CC: {founder_email})...")
        response = sg.send(message)
        print(f"[EMAIL] SendGrid response status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"[EMAIL] Founder followup email sent successfully to {email}")
            logger.info(f"Founder followup email sent to {email} (CC: {founder_email})")
            return True
        else:
            print(f"[EMAIL] SendGrid returned non-success status: {response.status_code}")
            logger.error(f"Failed to send founder followup to {email}: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Exception sending founder followup: {str(e)}")
        logger.error(f"Error sending founder followup to {email}: {str(e)}")
        return False


def send_marketing_campaign_email(
    email: str,
    first_name: str,
    subject: str,
    message: str,
    promo_code: str = None,
    unsubscribe_token: str = None,
) -> bool:
    """
    Send a marketing campaign email to a subscriber.

    Uses the marketing_campaign_email.html template with lime green branding.

    Args:
        email: Subscriber email address
        first_name: Subscriber first name
        subject: Email subject line
        message: Email body content (can contain {{first_name}}, {{founder_name}})
        promo_code: Optional promo code to include
        unsubscribe_token: Token for unsubscribe link

    Returns:
        True if sent successfully, False otherwise.
    """
    founder_name = os.getenv("FOUNDER_NAME", "Kristian")

    # Load template from file
    template_path = os.path.join(os.path.dirname(__file__), "email_templates", "marketing_campaign_email.html")
    with open(template_path, "r") as f:
        html_content = f.read()

    # Replace message variables
    processed_message = message.replace("{{first_name}}", first_name or "there")
    processed_message = processed_message.replace("{{founder_name}}", founder_name)

    # Build promo code section if provided
    promo_section = ""
    if promo_code:
        promo_section = f'''
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr>
                <td align="center" style="padding: 20px 0;">
                    <div style="background-color: #CCFF00; border-radius: 8px; padding: 20px; display: inline-block;">
                        <p style="margin: 0 0 10px 0; font-size: 14px; color: #1A1A1A;">Your exclusive promo code:</p>
                        <p style="margin: 0; font-size: 28px; font-weight: bold; color: #1A1A1A; letter-spacing: 2px;">{promo_code}</p>
                    </div>
                </td>
            </tr>
        </table>
        '''

    # Build unsubscribe URL — point at backend API directly (frontend has no route for this)
    api_base_url = os.getenv("API_BASE_URL", "https://tagparkingbohgithubio-production.up.railway.app")
    unsubscribe_url = f"{api_base_url}/api/marketing/unsubscribe/{unsubscribe_token}" if unsubscribe_token else f"{api_base_url}/api/marketing/unsubscribe"

    # Replace template placeholders
    html_content = html_content.replace("{{SUBJECT}}", subject)
    html_content = html_content.replace("{{FIRST_NAME}}", first_name or "there")
    html_content = html_content.replace("{{MESSAGE}}", processed_message.replace("\n", "<br>"))
    html_content = html_content.replace("{{PROMO_CODE_SECTION}}", promo_section)
    html_content = html_content.replace("{{FOUNDER_NAME}}", founder_name)
    html_content = html_content.replace("{{UNSUBSCRIBE_URL}}", unsubscribe_url)
    html_content = html_content.replace("{{PREVIEW_TEXT}}", subject[:100])

    print(f"[EMAIL] send_marketing_campaign_email called for: {email}, subject: {subject}")
    if is_staging_email_guard_active():
        print(f"[EMAIL] staging guard active — suppressed marketing campaign email to {email}")
        logger.info("[staging] would send marketing campaign email to %s — staging guard active", email)
        return True
    if not SENDGRID_API_KEY:
        print("[EMAIL] ERROR: SendGrid API key not configured!")
        logger.warning("SendGrid API key not configured - email not sent")
        return False

    try:
        message_obj = Mail(
            from_email=Email(FOUNDER_EMAIL, FOUNDER_NAME),
            to_emails=To(email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        print(f"[EMAIL] Sending marketing campaign via SendGrid...")
        response = sg.send(message_obj)
        print(f"[EMAIL] SendGrid response status: {response.status_code}")

        if response.status_code in (200, 201, 202):
            print(f"[EMAIL] Marketing campaign email sent successfully to {email}")
            logger.info(f"Marketing campaign email sent to {email}")
            return True
        else:
            print(f"[EMAIL] SendGrid returned non-success status: {response.status_code}")
            logger.error(f"Failed to send marketing campaign to {email}: {response.status_code}")
            return False

    except Exception as e:
        print(f"[EMAIL] Exception sending marketing campaign: {str(e)}")
        logger.error(f"Error sending marketing campaign to {email}: {str(e)}")
        return False


def send_vehicle_compliance_alert(
    booking_reference: str,
    customer_name: str,
    registration: str,
    dropoff_date: str,
    dropoff_time: str,
    tax_status: Optional[str],
    mot_status: Optional[str],
) -> bool:
    """Email Kristian when a booking's vehicle has a tax/MOT compliance issue.

    Recipient is `FOUNDER_EMAIL` (kristian@tagparking.co.uk by default).
    No admin link in body per spec — Kristian opens the booking himself.

    Staging guard: emails only fire when the environment is production.
    On non-prod environments the function logs what it would have sent
    and returns False (so the dedup timestamp does not get marked, and
    a real prod tick will still send the alert).
    """
    from config import get_settings  # local import — config not always loaded

    settings = get_settings()
    if settings.environment != "production":
        logger.info(
            "[staging] would send compliance alert to %s for booking %s "
            "(reg=%s tax=%s mot=%s) — staging guard active",
            FOUNDER_EMAIL, booking_reference, registration, tax_status, mot_status,
        )
        return False

    subject = f"[TAG] Vehicle compliance — {booking_reference}"
    html_content = f"""\
<p>Heads up — vehicle compliance check failed for upcoming booking.</p>
<table style="border-collapse: collapse;">
  <tr><td style="padding: 4px 12px 4px 0;"><strong>Booking</strong></td><td>{booking_reference}</td></tr>
  <tr><td style="padding: 4px 12px 4px 0;"><strong>Customer</strong></td><td>{customer_name}</td></tr>
  <tr><td style="padding: 4px 12px 4px 0;"><strong>Vehicle</strong></td><td>{registration}</td></tr>
  <tr><td style="padding: 4px 12px 4px 0;"><strong>Drop-off</strong></td><td>{dropoff_date} at {dropoff_time}</td></tr>
  <tr><td style="padding: 4px 12px 4px 0;"><strong>Tax</strong></td><td>{tax_status or '—'}</td></tr>
  <tr><td style="padding: 4px 12px 4px 0;"><strong>MOT</strong></td><td>{mot_status or '—'}</td></tr>
</table>
<p>One alert per booking per day; the daily 24h-before check will not re-send.</p>
"""
    return send_email(FOUNDER_EMAIL, subject, html_content)


def send_compliance_conflict_report(conflicts: list) -> bool:
    """Weekly digest: bookings whose tax/MOT expires DURING the parking window.

    Each item in `conflicts` is a dict with keys:
      reference, dropoff_date, pickup_date, customer, registration,
      vehicle_label, tax_conflict_date, mot_conflict_date

    Either tax_conflict_date or mot_conflict_date is a date (or None).
    Recipient is FOUNDER_EMAIL. Staging guard mirrors
    `send_vehicle_compliance_alert`.

    Returns True iff SendGrid 2xx'd. Returns False (without sending) on
    non-prod environments OR when `conflicts` is empty (no point pinging).
    """
    from config import get_settings

    settings = get_settings()
    if settings.environment != "production":
        logger.info(
            "[staging] would send conflict report (%s rows) — staging guard active",
            len(conflicts),
        )
        return False

    if not conflicts:
        logger.info("conflict report: no conflicts — skipping send")
        return False

    rows_html = []
    for c in conflicts:
        which = []
        if c.get("tax_conflict_date"):
            which.append(f"Tax due {c['tax_conflict_date'].strftime('%d/%m/%Y')}")
        if c.get("mot_conflict_date"):
            which.append(f"MOT expires {c['mot_conflict_date'].strftime('%d/%m/%Y')}")
        rows_html.append(
            "<tr>"
            f"<td>{c['reference']}</td>"
            f"<td>{c['dropoff_date'].strftime('%d/%m/%Y')} &ndash; {c['pickup_date'].strftime('%d/%m/%Y')}</td>"
            f"<td>{c['customer']}</td>"
            f"<td>{c['vehicle_label']}</td>"
            f"<td style='color:#822727;'>{', '.join(which)}</td>"
            "</tr>"
        )

    subject = f"[TAG] Weekly compliance conflicts — {len(conflicts)} booking{'s' if len(conflicts) != 1 else ''}"
    html_content = f"""\
<p>Hi,</p>
<p><strong>{len(conflicts)}</strong> upcoming booking{'s have' if len(conflicts) != 1 else ' has'} a vehicle whose
tax or MOT expires <em>during</em> the parking window. Customer arrives with
valid documents, leaves with an expired one.</p>
<p>This is separate from the daily 24h-before alert — that one only catches
already-failed compliance, not upcoming expiries inside the trip.</p>
<table style="border-collapse: collapse;" border="1" cellpadding="6">
  <thead>
    <tr style="background:#f7fafc;">
      <th align="left">Booking</th>
      <th align="left">Travel dates</th>
      <th align="left">Customer</th>
      <th align="left">Vehicle</th>
      <th align="left">Conflict</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows_html)}
  </tbody>
</table>
"""
    return send_email(FOUNDER_EMAIL, subject, html_content)


def send_bounce_alert_email(
    customer_email: str,
    event_type: str,
    reason: str,
    booking_reference: Optional[str] = None,
    raw_event: Optional[str] = None,
) -> bool:
    """Notify the founder that a SendGrid event indicates one of our outbound
    emails didn't reach a customer. Fired from the SendGrid event webhook for
    hard-failure event types (bounce, dropped, blocked, spamreport).

    The customer is silent — they think no email arrived. This alert turns
    that into an actionable signal so the founder can follow up by phone /
    SMS with the actual reason ("your email bounced — was it mistyped?").

    Args:
        customer_email: Address that failed.
        event_type: SendGrid event ("bounce", "dropped", "blocked", "spamreport").
        reason: Human-readable failure reason from SendGrid.
        booking_reference: TAG-XXX reference if we can resolve one.
        raw_event: Optional JSON dump of the raw SendGrid event for debugging.
    """
    subject = f"⚠️ Email bounce: {customer_email}"
    ref_line = (
        f"<p><strong>Booking reference:</strong> {booking_reference}</p>"
        if booking_reference else
        "<p><em>No matching booking found for this address.</em></p>"
    )
    raw_block = (
        f"<details><summary>Raw event</summary><pre style='font-size:11px;background:#f5f5f5;padding:8px;overflow:auto;'>{raw_event}</pre></details>"
        if raw_event else ""
    )
    html_content = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #c0392b;">Outbound email failure</h2>
  <p>SendGrid reported a <strong>{event_type}</strong> for an email Tag tried to send.</p>
  <table style="border-collapse: collapse; width: 100%;">
    <tr><td style="padding:6px 10px;border:1px solid #ddd;"><strong>Recipient</strong></td><td style="padding:6px 10px;border:1px solid #ddd;">{customer_email}</td></tr>
    <tr><td style="padding:6px 10px;border:1px solid #ddd;"><strong>Event type</strong></td><td style="padding:6px 10px;border:1px solid #ddd;">{event_type}</td></tr>
    <tr><td style="padding:6px 10px;border:1px solid #ddd;"><strong>Reason</strong></td><td style="padding:6px 10px;border:1px solid #ddd;">{reason or '(none provided)'}</td></tr>
  </table>
  {ref_line}
  <p style="margin-top: 16px;">
    <strong>What to do:</strong> the customer may not realise their email
    address doesn't work. Consider contacting them by phone or SMS to
    confirm the correct email address, then resend the relevant message.
  </p>
  {raw_block}
</div>
"""
    return send_email(FOUNDER_EMAIL, subject, html_content)
