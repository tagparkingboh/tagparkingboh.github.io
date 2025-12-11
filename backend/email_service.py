"""
Email service for sending marketing emails via SendGrid.
"""
import os
import logging
import secrets
import string
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)

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
    if not SENDGRID_API_KEY:
        logger.warning("SendGrid API key not configured - email not sent")
        return False

    try:
        message = Mail(
            from_email=Email(FROM_EMAIL, FROM_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )

        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        if response.status_code in (200, 201, 202):
            logger.info(f"Email sent successfully to {to_email}")
            return True
        else:
            logger.error(f"Failed to send email to {to_email}: {response.status_code}")
            return False

    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {str(e)}")
        return False


def send_welcome_email(first_name: str, email: str) -> bool:
    """Send welcome email to new subscriber."""
    subject = f"Welcome to TAG Parking, {first_name}!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: #ADFF2F; margin: 0; font-size: 28px; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .highlight {{ color: #ADFF2F; font-weight: bold; }}
            .button {{ display: inline-block; background: #ADFF2F; color: #1a1a2e; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 20px 0; }}
            .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>TAG Parking</h1>
            </div>
            <div class="content">
                <h2>Hi {first_name},</h2>

                <p>Thanks for joining the TAG Parking waitlist! We're excited to have you on board.</p>

                <p>We're building something special for Bournemouth Airport travellers - a <span class="highlight">premium Meet & Greet parking service</span> that takes the stress out of airport parking.</p>

                <p><strong>What you can expect:</strong></p>
                <ul>
                    <li>Drive directly to the terminal - we'll handle the parking</li>
                    <li>Your car returned to you when you land</li>
                    <li>Secure, insured parking at competitive prices</li>
                    <li>Simple online booking</li>
                </ul>

                <p>We'll be in touch soon with exclusive early access and a special discount code just for waitlist members.</p>

                <p>Safe travels!</p>
                <p><strong>The TAG Parking Team</strong></p>
            </div>
            <div class="footer">
                <p>TAG Parking | Bournemouth Airport</p>
                <p>You're receiving this because you signed up at tagparking.co.uk</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(email, subject, html_content)


def send_promo_code_email(first_name: str, email: str, promo_code: str = "TAG10") -> bool:
    """Send promo code email to subscriber."""
    subject = f"{first_name}, here's your exclusive TAG Parking discount!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ color: #ADFF2F; margin: 0; font-size: 28px; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .promo-box {{ background: #1a1a2e; color: white; padding: 25px; text-align: center; border-radius: 10px; margin: 20px 0; }}
            .promo-code {{ font-size: 36px; font-weight: bold; color: #ADFF2F; letter-spacing: 3px; }}
            .promo-text {{ font-size: 14px; color: #ccc; margin-top: 10px; }}
            .button {{ display: inline-block; background: #ADFF2F; color: #1a1a2e; padding: 15px 40px; text-decoration: none; border-radius: 5px; font-weight: bold; margin: 20px 0; font-size: 16px; }}
            .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>TAG Parking</h1>
            </div>
            <div class="content">
                <h2>Hi {first_name},</h2>

                <p>As promised, here's your <strong>exclusive waitlist discount</strong> for TAG Parking at Bournemouth Airport!</p>

                <div class="promo-box">
                    <div class="promo-code">{promo_code}</div>
                    <div class="promo-text">Use this code at checkout for 10% off your first booking</div>
                </div>

                <p>This code is exclusively for our early supporters like you. Use it when we launch to save on your next trip!</p>

                <p>We'll let you know as soon as bookings are open.</p>

                <p>Thanks for your patience and support!</p>
                <p><strong>The TAG Parking Team</strong></p>
            </div>
            <div class="footer">
                <p>TAG Parking | Bournemouth Airport</p>
                <p>You're receiving this because you signed up at tagparking.co.uk</p>
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
    pickup_time_window: str,
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
) -> bool:
    """
    Send booking confirmation email after successful payment.

    Args:
        email: Customer email address
        first_name: Customer first name
        booking_reference: Unique booking reference (e.g., TAG-XXXXXXXX)
        dropoff_date: Formatted drop-off date (e.g., "Saturday, 28 December 2025")
        dropoff_time: Drop-off time (e.g., "10:15")
        pickup_date: Formatted pickup date (e.g., "Saturday, 4 January 2026")
        pickup_time_window: Pickup window (e.g., "14:35 - 15:00")
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

    # Build discount section if applicable
    discount_section = ""
    if promo_code and discount_amount:
        discount_section = f"""
                        <tr style="color: #22c55e;">
                            <td style="padding: 8px 0; border-bottom: 1px solid #e5e5e5;">Promo Code ({promo_code})</td>
                            <td style="padding: 8px 0; border-bottom: 1px solid #e5e5e5; text-align: right;">-{discount_amount}</td>
                        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Booking Confirmation</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                <h1 style="color: #D9FF00; margin: 0; font-size: 32px; font-weight: bold;">TAG</h1>
                <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 14px;">Airport Parking</p>
            </div>

            <!-- Success Banner -->
            <div style="background: #22c55e; padding: 20px; text-align: center;">
                <div style="font-size: 40px; margin-bottom: 10px;">&#10003;</div>
                <h2 style="color: #ffffff; margin: 0; font-size: 24px;">Booking Confirmed!</h2>
            </div>

            <!-- Main Content -->
            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 16px; margin-bottom: 20px;">Hi {first_name},</p>

                <p style="font-size: 16px; margin-bottom: 25px;">
                    Thank you for booking with TAG Parking. Your parking is confirmed and we look forward to seeing you!
                </p>

                <!-- Booking Reference Box -->
                <div style="background: #1a1a2e; padding: 20px; text-align: center; border-radius: 8px; margin-bottom: 25px;">
                    <p style="color: #cccccc; margin: 0 0 5px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Your Booking Reference</p>
                    <p style="color: #D9FF00; margin: 0; font-size: 28px; font-weight: bold; letter-spacing: 2px;">{booking_reference}</p>
                </div>

                <!-- Booking Details -->
                <h3 style="color: #1a1a2e; margin: 25px 0 15px 0; font-size: 18px; border-bottom: 2px solid #D9FF00; padding-bottom: 10px;">Booking Details</h3>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; color: #666; width: 40%;">Drop-off</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; font-weight: 500;">
                            {dropoff_date}<br>
                            <span style="color: #1a1a2e; font-weight: bold;">{dropoff_time}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; color: #666;">Departure Flight</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5;">{departure_flight}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; color: #666;">Pick-up</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; font-weight: 500;">
                            {pickup_date}<br>
                            <span style="color: #1a1a2e; font-weight: bold;">{pickup_time_window}</span>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; color: #666;">Return Flight</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5;">{return_flight}</td>
                    </tr>
                </table>

                <!-- Vehicle Details -->
                <h3 style="color: #1a1a2e; margin: 25px 0 15px 0; font-size: 18px; border-bottom: 2px solid #D9FF00; padding-bottom: 10px;">Vehicle Details</h3>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; color: #666; width: 40%;">Vehicle</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5;">{vehicle_colour} {vehicle_make} {vehicle_model}</td>
                    </tr>
                    <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; color: #666;">Registration</td>
                        <td style="padding: 12px 0; border-bottom: 1px solid #e5e5e5; font-weight: bold; font-size: 16px;">{vehicle_registration}</td>
                    </tr>
                </table>

                <!-- Payment Summary -->
                <h3 style="color: #1a1a2e; margin: 25px 0 15px 0; font-size: 18px; border-bottom: 2px solid #D9FF00; padding-bottom: 10px;">Payment Summary</h3>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e5e5; color: #666;">Package</td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #e5e5e5; text-align: right;">{package_name}</td>
                    </tr>
                    {discount_section}
                    <tr style="font-size: 18px; font-weight: bold;">
                        <td style="padding: 12px 0; color: #1a1a2e;">Total Paid</td>
                        <td style="padding: 12px 0; text-align: right; color: #22c55e;">{amount_paid}</td>
                    </tr>
                </table>

                <!-- Important Info Box -->
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 4px solid #D9FF00; margin-bottom: 25px;">
                    <h4 style="color: #1a1a2e; margin: 0 0 10px 0; font-size: 16px;">Important Information</h4>
                    <ul style="color: #666; margin: 0; padding-left: 20px; line-height: 1.8;">
                        <li>Please arrive at the drop-off time shown above</li>
                        <li>Meet us at the <strong>Short Stay Car Park</strong> at Bournemouth Airport</li>
                        <li>Have your booking reference ready</li>
                        <li>We'll call you when we're on our way back with your car</li>
                    </ul>
                </div>

                <!-- Contact Section -->
                <div style="text-align: center; padding: 20px; background: #f8f9fa; border-radius: 8px;">
                    <p style="margin: 0 0 10px 0; color: #666;">Questions? We're here to help!</p>
                    <p style="margin: 0;">
                        <a href="mailto:booking@tagparking.co.uk" style="color: #1a1a2e; text-decoration: none; font-weight: 500;">booking@tagparking.co.uk</a>
                        <span style="color: #ccc; margin: 0 10px;">|</span>
                        <a href="tel:+447739106145" style="color: #1a1a2e; text-decoration: none; font-weight: 500;">07739 106145</a>
                    </p>
                </div>
            </div>

            <!-- Footer -->
            <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
                <p style="margin: 0 0 10px 0;">TAG Parking | Bournemouth International Airport</p>
                <p style="margin: 0;">© 2025 TAG Parking. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(email, subject, html_content)
