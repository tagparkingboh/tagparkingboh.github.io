"""
Email service for sending marketing emails via SendGrid.
"""
import os
import logging
import secrets
import string
from pathlib import Path
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)

# Get the directory where this file is located
EMAIL_TEMPLATES_DIR = Path(__file__).parent / "email_templates"

# SendGrid configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@tagparking.co.uk")
FROM_NAME = os.getenv("FROM_NAME", "TAG Parking")


def is_email_enabled() -> bool:
    """Check if email sending is enabled (API key is configured)."""
    return bool(SENDGRID_API_KEY)


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
    """Send promo code email to subscriber."""
    subject = f"{first_name}, here's a 10% off promo code"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #1a1a1a; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: #D9FF00; margin: 0; font-size: 28px; }}
            .content {{ background: #ffffff; padding: 30px; }}
            .promo-box {{ background: #1a1a1a; color: white; padding: 30px; text-align: center; border-radius: 16px; margin: 25px 0; }}
            .promo-code {{ font-size: 42px; font-weight: bold; color: #D9FF00; letter-spacing: 4px; margin-bottom: 10px; }}
            .promo-text {{ font-size: 16px; color: #ccc; }}
            .cta-section {{ text-align: center; margin: 30px 0; }}
            .button {{ display: inline-block; background: #1a1a1a; color: #D9FF00; padding: 14px 35px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; }}
            .tagline {{ font-size: 18px; font-weight: bold; color: #1a1a1a; margin: 25px 0 15px 0; }}
            .footer {{ background: #1a1a1a; padding: 25px; text-align: center; border-radius: 0 0 10px 10px; }}
            .footer p {{ color: #999; font-size: 12px; margin: 5px 0; }}
            .footer a {{ color: #D9FF00; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>TAG</h1>
            </div>
            <div class="content">
                <h2 style="margin-top: 0;">Hi {first_name},</h2>

                <p>Thanks for signing up! Although you weren't one of our winners this time, we'd still love to offer you an exclusive <strong>10% off</strong> promo code to use when you book your trip with Tag.</p>

                <div class="promo-box">
                    <div class="promo-code">{promo_code}</div>
                    <div class="promo-text">10% off your first booking</div>
                </div>

                <div class="cta-section">
                    <p style="font-size: 16px; margin-bottom: 15px;"><strong>Ready to book?</strong></p>
                    <a href="https://tagparking.co.uk" class="button" style="background: #1a1a1a; color: #D9FF00; display: inline-block; padding: 14px 35px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px;">Book now</a>
                </div>

                <p>Simply enter your code at checkout to apply the discount.</p>

                <p>If you have any questions or queries, please don't hesitate to contact us at <a href="mailto:info@tagparking.co.uk" style="color: #1a1a1a;">info@tagparking.co.uk</a>.</p>

                <p class="tagline">It's time to Tag it.</p>

                <p>Warm regards,</p>
                <p><strong>The Tag Team</strong></p>
            </div>
            <div class="footer">
                <p><strong style="color: #D9FF00;">TAG</strong> | Bournemouth Airport</p>
                <p>You're receiving this because you signed up at <a href="https://tagparking.co.uk">tagparking.co.uk</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(email, subject, html_content)


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
    departure_flight: str,
    return_flight: str,
    vehicle_make: str,
    vehicle_model: str,
    vehicle_colour: str,
    vehicle_registration: str,
    package_name: str,
    amount_paid: str,
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
        pickup_time: Pickup time - 45 mins after scheduled arrival (e.g., "15:20")
        departure_flight: Flight details (e.g., "TOM1234 to Tenerife (TFS)")
        return_flight: Return flight details (e.g., "TOM1235 from Tenerife (TFS)")
        vehicle_make: Vehicle make
        vehicle_model: Vehicle model
        vehicle_colour: Vehicle colour
        vehicle_registration: Registration plate
        package_name: Package name (e.g., "1 Week" or "2 Weeks")
        amount_paid: Amount paid (e.g., "£99.00")
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
        html_content = html_content.replace("{{DEPARTURE_FLIGHT}}", departure_flight)
        html_content = html_content.replace("{{RETURN_FLIGHT}}", return_flight)
        html_content = html_content.replace("{{VEHICLE_MAKE}}", vehicle_make)
        html_content = html_content.replace("{{VEHICLE_MODEL}}", vehicle_model)
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


def send_manual_booking_payment_email(
    email: str,
    first_name: str,
    dropoff_date: str,
    dropoff_time: str,
    pickup_date: str,
    pickup_time: str,
    vehicle_make: str,
    vehicle_model: str,
    vehicle_colour: str,
    vehicle_registration: str,
    amount: str,
    payment_link: str,
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
        html_content = html_content.replace("{{VEHICLE_MAKE}}", vehicle_make)
        html_content = html_content.replace("{{VEHICLE_MODEL}}", vehicle_model)
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
