"""
Background email scheduler using APScheduler.

Checks for subscribers who need welcome or promo emails and sends them.
- Welcome email: Sent 1 hour after subscription
- Promo code email: Sent 1 hour after welcome email (2 hours after subscription)
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from database import SessionLocal
from db_models import MarketingSubscriber
from email_service import send_welcome_email, send_promo_code_email, is_email_enabled, generate_promo_code

logger = logging.getLogger(__name__)

# Scheduler instance
scheduler = BackgroundScheduler()

# Configuration
WELCOME_EMAIL_DELAY_HOURS = 1  # Send welcome email 1 hour after signup
PROMO_EMAIL_DELAY_HOURS = 1   # Send promo email 1 hour after welcome email
CHECK_INTERVAL_MINUTES = 5     # Check for pending emails every 5 minutes


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def process_pending_welcome_emails():
    """
    Find subscribers who signed up more than WELCOME_EMAIL_DELAY_HOURS ago
    and haven't received their welcome email yet.
    """
    if not is_email_enabled():
        return

    db = get_db()
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=WELCOME_EMAIL_DELAY_HOURS)

        # Find subscribers who need welcome email
        pending = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.welcome_email_sent == False,
            MarketingSubscriber.subscribed_at <= cutoff_time,
        ).limit(10).all()  # Process 10 at a time to avoid overwhelming

        for subscriber in pending:
            logger.info(f"Sending welcome email to {subscriber.email}")

            success = send_welcome_email(
                first_name=subscriber.first_name,
                email=subscriber.email,
            )

            if success:
                subscriber.welcome_email_sent = True
                subscriber.welcome_email_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"Welcome email sent to {subscriber.email}")
            else:
                logger.error(f"Failed to send welcome email to {subscriber.email}")

    except Exception as e:
        logger.error(f"Error processing welcome emails: {str(e)}")
        db.rollback()
    finally:
        db.close()


def process_pending_promo_emails():
    """
    Find subscribers who received their welcome email more than
    PROMO_EMAIL_DELAY_HOURS ago and haven't received their promo code yet.
    """
    if not is_email_enabled():
        return

    db = get_db()
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=PROMO_EMAIL_DELAY_HOURS)

        # Find subscribers who need promo email
        pending = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.welcome_email_sent == True,
            MarketingSubscriber.promo_code_sent == False,
            MarketingSubscriber.welcome_email_sent_at <= cutoff_time,
        ).limit(10).all()

        for subscriber in pending:
            # Generate unique promo code if not already generated
            if not subscriber.promo_code:
                # Keep generating until we get a unique one
                for _ in range(10):  # Max 10 attempts
                    new_code = generate_promo_code()
                    existing = db.query(MarketingSubscriber).filter(
                        MarketingSubscriber.promo_code == new_code
                    ).first()
                    if not existing:
                        subscriber.promo_code = new_code
                        break
                else:
                    logger.error(f"Failed to generate unique promo code for {subscriber.email}")
                    continue

            logger.info(f"Sending promo code email to {subscriber.email} with code {subscriber.promo_code}")

            success = send_promo_code_email(
                first_name=subscriber.first_name,
                email=subscriber.email,
                promo_code=subscriber.promo_code,
            )

            if success:
                subscriber.promo_code_sent = True
                subscriber.promo_code_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"Promo code email sent to {subscriber.email}")
            else:
                logger.error(f"Failed to send promo code email to {subscriber.email}")

    except Exception as e:
        logger.error(f"Error processing promo emails: {str(e)}")
        db.rollback()
    finally:
        db.close()


def process_all_pending_emails():
    """Main job that processes all pending emails."""
    logger.debug("Checking for pending emails...")
    process_pending_welcome_emails()
    process_pending_promo_emails()


def start_scheduler():
    """Start the email scheduler."""
    if scheduler.running:
        logger.info("Scheduler already running")
        return

    # Add the job to check for pending emails
    scheduler.add_job(
        process_all_pending_emails,
        trigger=IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES),
        id="process_emails",
        name="Process pending marketing emails",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(f"Email scheduler started - checking every {CHECK_INTERVAL_MINUTES} minutes")


def stop_scheduler():
    """Stop the email scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Email scheduler stopped")


def trigger_immediate_check():
    """Trigger an immediate check for pending emails (useful for testing)."""
    process_all_pending_emails()
