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


def send_welcome_email(first_name: str, email: str) -> bool:
    """Send welcome email to new subscriber."""
    subject = f"Welcome to TAG, {first_name}!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #1a1a1a; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header img {{ max-width: 120px; }}
            .header h1 {{ color: #D9FF00; margin: 10px 0 0 0; font-size: 28px; }}
            .content {{ background: #ffffff; padding: 30px; }}
            .intro {{ font-size: 16px; color: #333; }}
            .steps {{ background: #f9f9f9; padding: 20px; margin: 25px 0; border-radius: 8px; }}
            .step {{ display: flex; align-items: flex-start; margin-bottom: 20px; }}
            .step:last-child {{ margin-bottom: 0; }}
            .step-number {{ background: #D9FF00; color: #1a1a1a; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0; margin-right: 15px; }}
            .step-content h4 {{ margin: 0 0 5px 0; color: #1a1a1a; font-size: 16px; }}
            .step-content p {{ margin: 0; color: #666; font-size: 14px; }}
            .cta-section {{ text-align: center; margin: 30px 0; }}
            .button {{ display: inline-block; background: #D9FF00; color: #1a1a1a; padding: 14px 35px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; }}
            .button:hover {{ background: #c4e600; }}
            .note {{ background: #f0f0f0; padding: 15px; border-radius: 6px; font-size: 14px; color: #555; margin: 20px 0; }}
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
                <p class="intro">Welcome to TAG — we're thrilled to have you with us!</p>

                <p>Our mission is simple: to provide an easier, faster and more cost-efficient meet & greet service for everyone. However you're travelling, we're here to give you a seamless experience from the moment you arrive.</p>

                <p><strong>No more sky-high fees, no more buses, no more treks to Zone F.</strong> Just your car, waiting for you when your trip is over.</p>

                <div class="steps">
                    <h3 style="margin-top: 0; color: #1a1a1a;">How does it work?</h3>

                    <div class="step">
                        <div class="step-number">1</div>
                        <div class="step-content">
                            <h4>Meet us at departures</h4>
                            <p>Simply drive to the terminal car park drop off and one of our drivers will be waiting for you</p>
                        </div>
                    </div>

                    <div class="step">
                        <div class="step-number">2</div>
                        <div class="step-content">
                            <h4>Sit back and enjoy your trip</h4>
                            <p>Relax while we park your car in our highly secured location, minutes from the airport</p>
                        </div>
                    </div>

                    <div class="step">
                        <div class="step-number">3</div>
                        <div class="step-content">
                            <h4>Pick up where you left off</h4>
                            <p>We then meet you at the same spot to hand your keys and car back to you</p>
                        </div>
                    </div>
                </div>

                <div class="note">
                    Before your scheduled meet and greet, you'll receive a confirmation email with all your details and the name of your greeter.
                </div>

                <div class="cta-section">
                    <p style="font-size: 16px; margin-bottom: 15px;"><strong>Ready to start your journey?</strong></p>
                    <a href="https://tagparking.co.uk/bookings" class="button">Book now</a>
                </div>

                <p>If you have any special requests or need assistance before your arrival, please don't hesitate to contact us at <a href="mailto:info@tagparking.co.uk" style="color: #1a1a1a;">info@tagparking.co.uk</a>.</p>

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


def send_promo_code_email(first_name: str, email: str, promo_code: str = "TAG10") -> bool:
    """Send promo code email to subscriber."""
    subject = f"{first_name}, here's your 10% off promo code!"

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
            .promo-box {{ background: #1a1a1a; color: white; padding: 30px; text-align: center; border-radius: 10px; margin: 25px 0; }}
            .promo-code {{ font-size: 42px; font-weight: bold; color: #D9FF00; letter-spacing: 4px; margin-bottom: 10px; }}
            .promo-text {{ font-size: 16px; color: #ccc; }}
            .cta-section {{ text-align: center; margin: 30px 0; }}
            .button {{ display: inline-block; background: #D9FF00; color: #1a1a1a; padding: 14px 35px; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; }}
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

                <p>Thanks for signing up! As promised, here's your exclusive <strong>10% off</strong> promo code for your first trip with TAG.</p>

                <div class="promo-box">
                    <div class="promo-code">{promo_code}</div>
                    <div class="promo-text">10% off your first booking</div>
                </div>

                <div class="cta-section">
                    <p style="font-size: 16px; margin-bottom: 15px;"><strong>Ready to book?</strong></p>
                    <a href="https://tagparking.co.uk/bookings" class="button">Book now</a>
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
