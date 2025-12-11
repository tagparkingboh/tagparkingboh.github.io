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
