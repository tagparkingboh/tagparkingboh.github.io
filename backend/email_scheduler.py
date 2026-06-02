"""
Background email scheduler using APScheduler.

Checks for subscribers who need welcome or promo emails and sends them.
- Welcome email: Sent 1 hour after subscription
- Promo code email: Sent 1 hour after welcome email (2 hours after subscription)
"""
import logging
import asyncio
from datetime import datetime, timedelta, time
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from database import SessionLocal
from db_models import MarketingSubscriber, Booking, BookingStatus, Customer
from email_service import send_welcome_email, send_promo_code_email, send_2_day_reminder_email, send_thank_you_email, send_founder_followup_email, is_email_enabled, generate_promo_code
import sms_service
from datetime import date as date_type
import pytz

logger = logging.getLogger(__name__)

# Scheduler instance
scheduler = BackgroundScheduler()

# Configuration
WELCOME_EMAIL_DELAY_MINUTES = 5  # Send welcome email 5 minutes after signup
PROMO_EMAIL_DELAY_HOURS = 1      # Send promo email 1 hour after welcome email (PAUSED)
THANK_YOU_EMAIL_DELAY_HOURS = 2  # Send thank you email 2 hours after booking completion
FOUNDER_FOLLOWUP_DELAY_HOURS = 1 # Send founder followup email 1 hour after pending booking
FOUNDER_FOLLOWUP_START_DATE = date_type(2026, 3, 1)  # Only process bookings from March 1st 2026
CHECK_INTERVAL_MINUTES = 1       # Check for pending emails every 1 minute


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def process_pending_welcome_emails(db: Session):
    """
    Find subscribers who signed up more than WELCOME_EMAIL_DELAY_MINUTES ago
    and haven't received their welcome email yet.
    """
    try:
        cutoff_time = datetime.utcnow() - timedelta(minutes=WELCOME_EMAIL_DELAY_MINUTES)

        # Find subscribers who need welcome email
        pending = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.welcome_email_sent == False,
            MarketingSubscriber.subscribed_at <= cutoff_time,
        ).limit(10).all()  # Process 10 at a time to avoid overwhelming

        for subscriber in pending:
            # Skip if already unsubscribed
            if subscriber.unsubscribed:
                continue

            logger.info(f"Sending welcome email to {subscriber.email}")

            success = send_welcome_email(
                first_name=subscriber.first_name,
                email=subscriber.email,
                unsubscribe_token=subscriber.unsubscribe_token,
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


def process_pending_promo_emails(db: Session):
    """
    Find subscribers who received their welcome email more than
    PROMO_EMAIL_DELAY_HOURS ago and haven't received their promo code yet.
    """
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


def process_pending_2day_reminders(db: Session):
    """
    Find confirmed bookings that are within 48 hours of their dropoff datetime
    (UK time) and haven't received the 2-day reminder yet.

    Uses exact datetime comparison: dropoff_date + dropoff_time must be within
    48 hours of the current UK time.
    """
    try:
        # Get current time in UK timezone
        uk_tz = pytz.timezone('Europe/London')
        now_uk = datetime.now(uk_tz)

        # Calculate the cutoff: 48 hours from now in UK time
        cutoff_datetime = now_uk + timedelta(hours=48)
        cutoff_date = cutoff_datetime.date()

        # First, get candidate bookings with a broad date filter
        # (we'll do precise datetime filtering in Python)
        # Include bookings up to cutoff_date + 1 to account for edge cases
        candidate_bookings = db.query(Booking).filter(
            Booking.reminder_2day_sent == False,
            Booking.status == BookingStatus.CONFIRMED,
            Booking.dropoff_date <= cutoff_date + timedelta(days=1),
            Booking.dropoff_date >= now_uk.date(),  # Don't send for past bookings
        ).limit(50).all()

        # Filter to only bookings within exactly 48 hours
        pending = []
        for booking in candidate_bookings:
            # Combine dropoff_date + dropoff_time into a datetime
            dropoff_time = booking.dropoff_time or time(0, 0)
            dropoff_datetime = uk_tz.localize(datetime.combine(booking.dropoff_date, dropoff_time))

            # Check if dropoff is within 48 hours from now
            if now_uk <= dropoff_datetime <= cutoff_datetime:
                pending.append(booking)

        # Limit to 10 at a time to avoid overwhelming
        pending = pending[:10]

        for booking in pending:
            # Get customer details
            customer = db.query(Customer).filter(Customer.id == booking.customer_id).first()
            if not customer:
                logger.error(f"Customer not found for booking {booking.reference}")
                continue

            # Get flight departure time from the booking's stored column
            # We no longer use FlightDeparture lookup - all times are stored directly on the booking
            flight_departure_time = "TBC"
            if booking.flight_departure_time:
                flight_departure_time = booking.flight_departure_time.strftime("%H:%M")

            # Format dropoff date
            dropoff_date_formatted = booking.dropoff_date.strftime("%A, %d %B %Y")
            dropoff_time_formatted = booking.dropoff_time.strftime("%H:%M")

            logger.info(f"Sending 2-day reminder to {customer.email} for booking {booking.reference}")

            success = send_2_day_reminder_email(
                email=customer.email,
                first_name=customer.first_name,
                last_name=customer.last_name,
                booking_reference=booking.reference,
                dropoff_date=dropoff_date_formatted,
                dropoff_time=dropoff_time_formatted,
                flight_departure_time=flight_departure_time,
            )

            if success:
                booking.reminder_2day_sent = True
                booking.reminder_2day_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"2-day reminder sent to {customer.email} for booking {booking.reference}")

                # Also send SMS reminder if enabled
                if sms_service.is_sms_enabled():
                    try:
                        asyncio.run(sms_service.send_reminder_2day_sms(booking, db))
                        logger.info(f"2-day reminder SMS sent for booking {booking.reference}")
                    except Exception as sms_error:
                        logger.error(f"Failed to send 2-day reminder SMS: {str(sms_error)}")
            else:
                logger.error(f"Failed to send 2-day reminder to {customer.email}")

    except Exception as e:
        logger.error(f"Error processing 2-day reminders: {str(e)}")
        db.rollback()


def process_pending_thankyou_emails(db: Session):
    """
    Find completed bookings that were completed more than 2 hours ago
    and haven't received the thank you email yet.
    """
    try:
        # Calculate cutoff: 2 hours ago
        cutoff_time = datetime.utcnow() - timedelta(hours=THANK_YOU_EMAIL_DELAY_HOURS)

        # Find completed bookings that need thank you email
        pending = db.query(Booking).filter(
            Booking.status == BookingStatus.COMPLETED,
            Booking.thank_you_email_sent == False,
            Booking.completed_at != None,
            Booking.completed_at <= cutoff_time,
        ).limit(10).all()

        for booking in pending:
            # Get customer details
            customer = db.query(Customer).filter(Customer.id == booking.customer_id).first()
            if not customer:
                logger.error(f"Customer not found for booking {booking.reference}")
                continue

            logger.info(f"Sending thank you email to {customer.email} for booking {booking.reference}")

            success = send_thank_you_email(
                email=customer.email,
                first_name=customer.first_name,
            )

            if success:
                booking.thank_you_email_sent = True
                booking.thank_you_email_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"Thank you email sent to {customer.email} for booking {booking.reference}")

                # Also send SMS if enabled
                if sms_service.is_sms_enabled():
                    try:
                        asyncio.run(sms_service.send_thank_you_sms(booking, db))
                        logger.info(f"Thank you SMS sent for booking {booking.reference}")
                    except Exception as sms_error:
                        logger.error(f"Failed to send thank you SMS: {str(sms_error)}")
            else:
                logger.error(f"Failed to send thank you email to {customer.email}")

    except Exception as e:
        logger.error(f"Error processing thank you emails: {str(e)}")
        db.rollback()


def process_pending_founder_followups(db: Session):
    """
    Find customers who abandoned at the contact details stage (no bookings).
    Sends a personal follow-up email from the founder.

    Note: Customers with pending bookings (abandoned at payment stage) are
    handled manually via the "Send Founder Email" button in Admin > Bookings.

    Eligibility criteria:
    1. Customer hasn't received founder followup email yet
    2. Customer's last activity was more than 1 hour ago
    3. Customer has ZERO bookings (abandoned at contact details, not payment)
    4. Activity must be on or after March 1st 2026:
       - New customers: created_at >= March 1st 2026
       - Existing customers: updated_at >= March 1st 2026
    """
    try:
        # Calculate cutoff: 1 hour ago (UK time, timezone-aware)
        uk_tz = pytz.timezone('Europe/London')
        now_uk = datetime.now(uk_tz)
        cutoff_time = now_uk - timedelta(hours=FOUNDER_FOLLOWUP_DELAY_HOURS)
        start_datetime = uk_tz.localize(datetime(
            FOUNDER_FOLLOWUP_START_DATE.year,
            FOUNDER_FOLLOWUP_START_DATE.month,
            FOUNDER_FOLLOWUP_START_DATE.day
        ))

        from sqlalchemy import or_, and_, not_, exists
        from sqlalchemy.orm import aliased

        # Subquery to check if customer has ANY booking (regardless of status)
        # Customers with pending bookings are handled manually via Admin CTA
        has_any_booking = db.query(Booking).filter(
            Booking.customer_id == Customer.id
        ).exists()

        # Find customers who:
        # 1. Haven't received founder followup
        # 2. Have ZERO bookings (abandoned at contact details stage)
        # 3. Either:
        #    a) Created after March 1st AND created more than 1 hour ago, OR
        #    b) Created before March 1st AND updated after March 1st AND updated more than 1 hour ago
        eligible_customers = db.query(Customer).filter(
            Customer.founder_followup_sent == False,
            Customer.email != None,
            Customer.email != "",
            ~has_any_booking,
            or_(
                # New customer created after start date
                and_(
                    Customer.created_at >= start_datetime,
                    Customer.created_at <= cutoff_time
                ),
                # Existing customer updated after start date
                and_(
                    Customer.created_at < start_datetime,
                    Customer.updated_at != None,
                    Customer.updated_at >= start_datetime,
                    Customer.updated_at <= cutoff_time
                )
            )
        ).limit(10).all()

        for customer in eligible_customers:
            # Determine last activity time for logging
            if customer.updated_at and customer.updated_at >= start_datetime:
                last_activity = customer.updated_at
            else:
                last_activity = customer.created_at

            logger.info(f"Sending founder followup to {customer.email} (last activity: {last_activity})")

            success = send_founder_followup_email(
                email=customer.email,
                first_name=customer.first_name,
            )

            if success:
                customer.founder_followup_sent = True
                customer.founder_followup_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"Founder followup sent to {customer.email}")
            else:
                logger.error(f"Failed to send founder followup to {customer.email}")

    except Exception as e:
        logger.error(f"Error processing founder followups: {str(e)}")
        db.rollback()


def process_pending_referral_invites(db: Session):
    """Send referral invites/reminders for completed bookings."""
    try:
        from referral_service import (
            process_eligible_referral_invites,
            process_pending_referral_codes,
            process_referral_invite_reminders,
        )

        invited = process_eligible_referral_invites(db)
        reminded = process_referral_invite_reminders(db)
        coded = process_pending_referral_codes(db)
        if invited or reminded or coded:
            logger.info(
                "Processed referral emails: %s invite(s), %s reminder(s), %s code(s)",
                invited,
                reminded,
                coded,
            )
    except Exception as e:
        logger.error(f"Error processing referral invites: {str(e)}")
        db.rollback()


def process_pending_dvla_rechecks(db: Session):
    """24h-before DVLA refresh + compliance alert for tomorrow's bookings.

    Scope (locked 2026-05-03): bookings with status in {CONFIRMED, REFUNDED}
    and dropoff_date == tomorrow (Europe/London).

    Per-vehicle dedup: skip the DVLA refresh if `vehicles.dvla_checked_at`
    is already in today's UK day window (same vehicle on multiple bookings
    only hits DVLA once per day). Per-booking dedup: skip the alert email
    if `bookings.last_compliance_alert_sent_at` is in today's UK day window
    (one alert per booking per day, even across multiple scheduler ticks).

    The email itself self-guards on environment so staging never reaches
    Kristian — see send_vehicle_compliance_alert.
    """
    from db_models import Vehicle
    from dvla_compliance import refresh_vehicle_dvla, should_alert
    from email_service import send_vehicle_compliance_alert
    from config import get_settings

    try:
        settings = get_settings()
        api_key = (
            settings.dvla_api_key_prod
            if settings.environment == "production"
            else settings.dvla_api_key_test
        )
        if not api_key:
            logger.warning("DVLA API key not configured — skipping recheck pass")
            return

        uk_tz = pytz.timezone("Europe/London")
        now_uk = datetime.now(uk_tz)
        tomorrow = (now_uk + timedelta(days=1)).date()
        today_start_uk = uk_tz.localize(
            datetime.combine(now_uk.date(), time.min)
        )

        bookings = db.query(Booking).filter(
            Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.REFUNDED]),
            Booking.dropoff_date == tomorrow,
        ).all()

        for booking in bookings:
            vehicle = booking.vehicle
            if vehicle is None:
                continue

            # Skip DVLA refresh if this vehicle was already checked today
            already_checked_today = (
                vehicle.dvla_checked_at is not None
                and vehicle.dvla_checked_at >= today_start_uk
            )
            if already_checked_today:
                is_alertable = should_alert(vehicle.tax_status, vehicle.mot_status)
            else:
                is_alertable = refresh_vehicle_dvla(
                    db,
                    vehicle,
                    api_key=api_key,
                    is_production=(settings.environment == "production"),
                )

            if not is_alertable:
                continue

            # Per-booking dedup: skip if already alerted today
            if (
                booking.last_compliance_alert_sent_at is not None
                and booking.last_compliance_alert_sent_at >= today_start_uk
            ):
                continue

            customer_name = f"{booking.customer_first_name or booking.customer.first_name} {booking.customer_last_name or booking.customer.last_name}".strip()
            sent = send_vehicle_compliance_alert(
                booking_reference=booking.reference,
                customer_name=customer_name,
                registration=vehicle.registration,
                dropoff_date=booking.dropoff_date.strftime("%d/%m/%Y"),
                dropoff_time=booking.dropoff_time.strftime("%H:%M") if booking.dropoff_time else "—",
                tax_status=vehicle.tax_status,
                mot_status=vehicle.mot_status,
            )
            if sent:
                # Only mark dedup if SendGrid actually accepted the message —
                # a staging-guard skip returns False so the prod tick can
                # still alert.
                booking.last_compliance_alert_sent_at = datetime.now(uk_tz)
                db.commit()

    except Exception as e:
        logger.exception("Error processing DVLA rechecks: %s", e)
        db.rollback()


def process_weekly_conflict_report(db: Session = None):
    """Weekly digest: bookings whose tax/MOT expires INSIDE the parking window.

    Scope: status IN (CONFIRMED, REFUNDED) AND
           (tax_status='Taxed' AND tax_due_date BETWEEN dropoff AND pickup)
        OR (mot_status='Valid' AND mot_expiry_date BETWEEN dropoff AND pickup)

    Excludes vehicles already failing compliance — those are handled by the
    daily 24h-before alert. This report is the "look ahead at trips that
    will fail mid-stay" view.

    Wired to APScheduler CronTrigger (Mon 09:00 Europe/London) — see
    start_scheduler. The function also accepts an optional `db` so it can
    be called directly from tests.
    """
    from db_models import Vehicle, Customer
    from email_service import send_compliance_conflict_report
    from sqlalchemy import or_, and_

    own_session = False
    if db is None:
        db = get_db()
        own_session = True
    try:
        query = (
            db.query(Booking, Vehicle, Customer)
            .join(Vehicle, Vehicle.id == Booking.vehicle_id)
            .outerjoin(Customer, Customer.id == Booking.customer_id)
            .filter(
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.REFUNDED]),
                or_(
                    and_(
                        Vehicle.tax_status == "Taxed",
                        Vehicle.tax_due_date.between(
                            Booking.dropoff_date, Booking.pickup_date
                        ),
                    ),
                    and_(
                        Vehicle.mot_status == "Valid",
                        Vehicle.mot_expiry_date.between(
                            Booking.dropoff_date, Booking.pickup_date
                        ),
                    ),
                ),
            )
            .order_by(Booking.dropoff_date.asc())
        )
        rows = query.all()

        conflicts = []
        for booking, vehicle, customer in rows:
            first = booking.customer_first_name or (customer.first_name if customer else "")
            last = booking.customer_last_name or (customer.last_name if customer else "")
            tax_conf = (
                vehicle.tax_due_date
                if vehicle.tax_status == "Taxed"
                and vehicle.tax_due_date is not None
                and booking.dropoff_date <= vehicle.tax_due_date <= booking.pickup_date
                else None
            )
            mot_conf = (
                vehicle.mot_expiry_date
                if vehicle.mot_status == "Valid"
                and vehicle.mot_expiry_date is not None
                and booking.dropoff_date <= vehicle.mot_expiry_date <= booking.pickup_date
                else None
            )
            label_parts = [vehicle.colour, vehicle.make]
            vehicle_label = f"{vehicle.registration} ({' '.join(p for p in label_parts if p)})".strip()
            conflicts.append({
                "reference": booking.reference,
                "dropoff_date": booking.dropoff_date,
                "pickup_date": booking.pickup_date,
                "customer": f"{first} {last}".strip() or "—",
                "registration": vehicle.registration,
                "vehicle_label": vehicle_label,
                "tax_conflict_date": tax_conf,
                "mot_conflict_date": mot_conf,
            })

        logger.info(
            "weekly conflict report: %s booking(s) with mid-trip expiry",
            len(conflicts),
        )
        send_compliance_conflict_report(conflicts)
    except Exception as e:
        logger.exception("weekly conflict report failed: %s", e)
    finally:
        if own_session:
            db.close()


def process_all_pending_emails():
    """Main job that processes all pending emails using a single DB connection."""
    if not is_email_enabled():
        return

    logger.debug("Checking for pending emails...")

    # Use a single database connection for all email processing
    db = get_db()
    try:
        process_pending_welcome_emails(db)
        process_pending_2day_reminders(db)
        process_pending_thankyou_emails(db)
        process_pending_founder_followups(db)
        process_pending_referral_invites(db)
        process_pending_dvla_rechecks(db)
        # PAUSED: Promo code emails - uncomment when ready to send
        # process_pending_promo_emails(db)
    finally:
        db.close()


def cleanup_old_snapshots():
    """Remove pool snapshots older than 7 days to prevent table bloat."""
    try:
        db = get_db()
        try:
            from db_models import DbPoolSnapshot
            cutoff = datetime.utcnow() - timedelta(days=7)
            deleted = db.query(DbPoolSnapshot).filter(
                DbPoolSnapshot.created_at < cutoff
            ).delete()
            db.commit()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old pool snapshots")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to cleanup old snapshots: {e}")


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

    # Pool snapshots are now event-driven (recorded when thresholds are crossed)
    # See database.py for threshold-based snapshot recording

    # Add job to cleanup old snapshots once per day
    scheduler.add_job(
        cleanup_old_snapshots,
        trigger=IntervalTrigger(hours=24),
        id="cleanup_pool_snapshots",
        name="Cleanup old pool snapshots",
        replace_existing=True,
    )

    # Weekly DVLA compliance conflict report — Monday 09:00 Europe/London.
    # Surfaces upcoming bookings whose tax/MOT will expire DURING the
    # parking window (the daily 24h-before scheduler doesn't catch these).
    # `misfire_grace_time=3600` keeps the report alive across short
    # restarts: if the server is down at 09:00 and back up by 10:00,
    # the job still fires.
    scheduler.add_job(
        process_weekly_conflict_report,
        trigger=CronTrigger(
            day_of_week="mon", hour=9, minute=0,
            timezone=pytz.timezone("Europe/London"),
        ),
        id="weekly_conflict_report",
        name="Weekly DVLA compliance conflict report",
        replace_existing=True,
        misfire_grace_time=3600,
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


# Legacy function wrappers for backward compatibility (if called directly)
def _process_welcome_emails_standalone():
    if not is_email_enabled():
        return
    db = get_db()
    try:
        process_pending_welcome_emails(db)
    finally:
        db.close()


def _process_2day_reminders_standalone():
    if not is_email_enabled():
        return
    db = get_db()
    try:
        process_pending_2day_reminders(db)
    finally:
        db.close()


def _process_thankyou_emails_standalone():
    if not is_email_enabled():
        return
    db = get_db()
    try:
        process_pending_thankyou_emails(db)
    finally:
        db.close()


def _process_founder_followups_standalone():
    if not is_email_enabled():
        return
    db = get_db()
    try:
        process_pending_founder_followups(db)
    finally:
        db.close()
