"""Referral program state machine and promo-code integration helpers."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from db_models import (
    Booking,
    BookingStatus,
    Customer,
    PromoCode,
    Promotion,
    ReferralAttribution,
    ReferralProgram,
)


PROGRAM_STATUS_ELIGIBLE = "eligible"
PROGRAM_STATUS_INVITED = "invited"
PROGRAM_STATUS_REMINDED = "reminded"
PROGRAM_STATUS_OPTED_IN = "opted_in"
PROGRAM_STATUS_OPTED_OUT = "opted_out"

ATTRIBUTION_STATUS_PENDING = "pending"
ATTRIBUTION_STATUS_QUALIFIED = "qualified"
ATTRIBUTION_STATUS_DISQUALIFIED = "disqualified"

REFERRAL_REWARD_THRESHOLD = 6
INVITE_DELAY_DAYS = 2
REMINDER_DELAY_DAYS = 28
TOKEN_TTL_DAYS = 90

FRIEND_PROMOTION_NAME = "Referral Friend 10%"
REWARD_PROMOTION_NAME = "Referral Reward Free Week"


class ReferralTokenError(ValueError):
    """Raised when a referral response token is invalid or expired."""


def referral_invites_enabled() -> bool:
    return os.getenv("REFERRAL_INVITES_ENABLED", "true").lower() not in {"0", "false", "no"}


def referral_codes_enabled() -> bool:
    return os.getenv("REFERRAL_CODES_ENABLED", "true").lower() not in {"0", "false", "no"}


def referral_rewards_enabled() -> bool:
    return os.getenv("REFERRAL_REWARDS_ENABLED", "true").lower() not in {"0", "false", "no"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_secret() -> bytes:
    secret = (
        os.getenv("REFERRAL_TOKEN_SECRET")
        or os.getenv("SECRET_KEY")
        or os.getenv("STRIPE_WEBHOOK_SECRET")
    )
    if not secret:
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment not in {"development", "local", "test"}:
            raise RuntimeError("REFERRAL_TOKEN_SECRET or SECRET_KEY must be configured")
        secret = "development-referral-token-secret"
    return secret.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def generate_response_token(program: ReferralProgram, expires_at: Optional[datetime] = None) -> str:
    expires = expires_at or (_now() + timedelta(days=TOKEN_TTL_DAYS))
    payload = {
        "program_id": program.id,
        "customer_id": program.customer_id,
        "exp": int(expires.timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = _b64(payload_bytes)
    signature = hmac.new(_token_secret(), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_b64(signature)}"


def validate_response_token(db: Session, token: str) -> ReferralProgram:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected = hmac.new(_token_secret(), encoded_payload.encode("ascii"), hashlib.sha256).digest()
        supplied = _unb64(encoded_signature)
        if not hmac.compare_digest(expected, supplied):
            raise ReferralTokenError("Invalid referral token")
        payload = json.loads(_unb64(encoded_payload).decode("utf-8"))
    except Exception as exc:
        raise ReferralTokenError("Invalid referral token") from exc

    if int(payload.get("exp", 0)) < int(_now().timestamp()):
        raise ReferralTokenError("Referral token has expired")

    program = db.query(ReferralProgram).filter(
        ReferralProgram.id == payload.get("program_id"),
        ReferralProgram.customer_id == payload.get("customer_id"),
    ).first()
    if not program:
        raise ReferralTokenError("Referral invite was not found")
    return program


def _valid_email(email: Optional[str]) -> bool:
    return bool(email and "@" in email and "." in email.rsplit("@", 1)[-1])


def _api_base_url() -> str:
    return os.getenv("API_BASE_URL", "https://tagparkingbohgithubio-production.up.railway.app").rstrip("/")


def _response_urls(program: ReferralProgram) -> tuple[str, str]:
    token = generate_response_token(program)
    base = _api_base_url()
    return (
        f"{base}/api/referrals/respond?token={token}&decision=yes",
        f"{base}/api/referrals/respond?token={token}&decision=no",
    )


def process_eligible_referral_invites(db: Session, limit: int = 25, now: Optional[datetime] = None) -> int:
    """Invite customers whose first completed booking is at least 2 days old."""
    if not referral_invites_enabled():
        return 0

    from email_service import send_referral_invite_email

    current = now or _now()
    cutoff = current - timedelta(days=INVITE_DELAY_DAYS)
    candidates = (
        db.query(Customer)
        .join(Booking, Booking.customer_id == Customer.id)
        .outerjoin(ReferralProgram, ReferralProgram.customer_id == Customer.id)
        .filter(
            ReferralProgram.id == None,
            Booking.status == BookingStatus.COMPLETED,
            Booking.completed_at != None,
            Booking.completed_at <= cutoff,
        )
        .order_by(Booking.completed_at.asc())
        .limit(limit)
        .all()
    )

    sent = 0
    seen_customer_ids = set()
    for customer in candidates:
        if customer.id in seen_customer_ids:
            continue
        seen_customer_ids.add(customer.id)
        if not _valid_email(customer.email):
            continue

        existing = db.query(ReferralProgram).filter(ReferralProgram.customer_id == customer.id).first()
        if existing:
            continue

        program = ReferralProgram(customer_id=customer.id, status=PROGRAM_STATUS_ELIGIBLE)
        db.add(program)
        db.flush()

        yes_url, no_url = _response_urls(program)
        if send_referral_invite_email(customer.first_name, customer.email, yes_url, no_url):
            program.status = PROGRAM_STATUS_INVITED
            program.invite_sent_at = current
            db.commit()
            sent += 1
        else:
            db.rollback()

    return sent


def send_manual_referral_invite(
    db: Session,
    first_name: str,
    last_name: str,
    email: str,
    now: Optional[datetime] = None,
) -> tuple[ReferralProgram, Customer, bool, bool]:
    """Create/reuse a customer and send a one-off referral invite.

    Returns (program, customer, created_customer, sent_invite). Existing opted-in
    customers are left alone so admins do not send a stale opt-in prompt to
    someone who already has a referral code.
    """
    if not referral_invites_enabled():
        raise ValueError("Referral invites are disabled")

    from email_service import send_referral_invite_email

    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    normalized_email = (email or "").strip().lower()
    if not first_name or not last_name or not _valid_email(normalized_email):
        raise ValueError("First name, last name, and a valid email are required")

    current = now or _now()
    customer = (
        db.query(Customer)
        .filter(func.lower(Customer.email) == normalized_email)
        .first()
    )
    created_customer = False
    if not customer:
        customer = Customer(
            first_name=first_name,
            last_name=last_name,
            email=normalized_email,
            phone="",
            billing_country="United Kingdom",
        )
        db.add(customer)
        db.flush()
        created_customer = True

    program = db.query(ReferralProgram).filter(ReferralProgram.customer_id == customer.id).first()
    if not program:
        program = ReferralProgram(customer_id=customer.id, status=PROGRAM_STATUS_ELIGIBLE)
        db.add(program)
        db.flush()

    if program.status == PROGRAM_STATUS_OPTED_IN:
        return program, customer, created_customer, False

    yes_url, no_url = _response_urls(program)
    if not send_referral_invite_email(customer.first_name, customer.email, yes_url, no_url):
        db.rollback()
        raise ValueError("Failed to send referral invite email")

    program.status = PROGRAM_STATUS_INVITED
    program.invite_sent_at = current
    program.reminder_sent_at = None
    program.responded_at = None
    db.commit()
    db.refresh(program)
    db.refresh(customer)
    return program, customer, created_customer, True


def process_referral_invite_reminders(db: Session, limit: int = 25, now: Optional[datetime] = None) -> int:
    """Send one reminder 4 weeks after an unanswered invite."""
    if not referral_invites_enabled():
        return 0

    from email_service import send_referral_invite_reminder_email

    current = now or _now()
    cutoff = current - timedelta(days=REMINDER_DELAY_DAYS)
    programs = (
        db.query(ReferralProgram)
        .filter(
            ReferralProgram.status == PROGRAM_STATUS_INVITED,
            ReferralProgram.invite_sent_at != None,
            ReferralProgram.invite_sent_at <= cutoff,
            ReferralProgram.reminder_sent_at == None,
        )
        .limit(limit)
        .all()
    )

    sent = 0
    for program in programs:
        customer = program.customer or db.query(Customer).filter(Customer.id == program.customer_id).first()
        if not customer or not _valid_email(customer.email):
            continue
        yes_url, no_url = _response_urls(program)
        if send_referral_invite_reminder_email(customer.first_name, customer.email, yes_url, no_url):
            program.status = PROGRAM_STATUS_REMINDED
            program.reminder_sent_at = current
            db.commit()
            sent += 1
        else:
            db.rollback()
    return sent


def process_pending_referral_codes(db: Session, limit: int = 25, now: Optional[datetime] = None) -> int:
    """Create or resend codes for opted-in customers that still need delivery."""
    if not referral_codes_enabled():
        return 0

    current = now or _now()
    programs = (
        db.query(ReferralProgram)
        .filter(
            ReferralProgram.status == PROGRAM_STATUS_OPTED_IN,
        )
        .limit(limit)
        .all()
    )

    processed = 0
    for program in programs:
        code = None
        if program.referral_code_id:
            code = db.query(PromoCode).filter(PromoCode.id == program.referral_code_id).first()
            if code and code.email_sent:
                continue
        ensure_referral_code(db, program, now=current)
        db.commit()
        processed += 1
    return processed


def respond_to_referral_invite(
    db: Session,
    token: str,
    decision: str,
    now: Optional[datetime] = None,
) -> ReferralProgram:
    decision_normalized = (decision or "").strip().lower()
    if decision_normalized not in {"yes", "no"}:
        raise ReferralTokenError("Referral decision must be yes or no")

    program = validate_response_token(db, token)
    current = now or _now()

    if program.status in {PROGRAM_STATUS_OPTED_IN, PROGRAM_STATUS_OPTED_OUT}:
        return program

    if decision_normalized == "no":
        program.status = PROGRAM_STATUS_OPTED_OUT
        program.responded_at = program.responded_at or current
        db.commit()
        return program

    program.status = PROGRAM_STATUS_OPTED_IN
    program.responded_at = program.responded_at or current
    if referral_codes_enabled():
        ensure_referral_code(db, program, now=current)
    db.commit()
    return program


def recompute_referral_progress(db: Session, program: ReferralProgram) -> int:
    # Make in-session attribution status changes visible to the count query.
    db.flush()
    qualified_count = db.query(ReferralAttribution).filter(
        ReferralAttribution.referral_program_id == program.id,
        ReferralAttribution.is_self_use == False,
        ReferralAttribution.status == ATTRIBUTION_STATUS_QUALIFIED,
    ).count()
    program.qualified_referral_count = qualified_count
    return qualified_count


def disqualify_referral_for_booking(
    db: Session,
    booking: Optional[Booking],
) -> Optional[ReferralAttribution]:
    if not booking:
        return None

    attribution = db.query(ReferralAttribution).filter(ReferralAttribution.booking_id == booking.id).first()
    if not attribution:
        return None

    if attribution.status == ATTRIBUTION_STATUS_QUALIFIED:
        attribution.status = ATTRIBUTION_STATUS_DISQUALIFIED
        attribution.qualified_at = None

    program = attribution.program or db.query(ReferralProgram).filter(
        ReferralProgram.id == attribution.referral_program_id
    ).first()
    if program:
        recompute_referral_progress(db, program)
    return attribution


def _generate_code(prefix: str) -> str:
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "").replace("L", "")
    return f"{prefix}-{''.join(secrets.choice(chars) for _ in range(4))}-{''.join(secrets.choice(chars) for _ in range(4))}"


def _unique_code(db: Session, prefix: str) -> str:
    for _ in range(20):
        code = _generate_code(prefix)
        if not db.query(PromoCode).filter(PromoCode.code == code).first():
            return code
    raise RuntimeError(f"Unable to generate unique {prefix} promo code")


def _get_or_create_promotion(db: Session, name: str, discount_percent: int, discount_type: str, prefix: str) -> Promotion:
    promotion = db.query(Promotion).filter(Promotion.name == name).first()
    if promotion:
        return promotion
    promotion = Promotion(
        name=name,
        description="Referral program promotion",
        discount_percent=discount_percent,
        discount_type=discount_type,
        code_prefix=prefix,
        total_codes=0,
        codes_sent=0,
        codes_used=0,
        created_by="system",
    )
    db.add(promotion)
    db.flush()
    return promotion


def ensure_referral_code(db: Session, program: ReferralProgram, now: Optional[datetime] = None) -> PromoCode:
    from email_service import send_referral_code_email

    customer = program.customer or db.query(Customer).filter(Customer.id == program.customer_id).first()
    if not customer:
        raise ValueError("Referral program customer not found")

    current = now or _now()
    promotion = None
    code = None
    if program.referral_code_id:
        code = db.query(PromoCode).filter(PromoCode.id == program.referral_code_id).first()
    if not code:
        promotion = _get_or_create_promotion(db, FRIEND_PROMOTION_NAME, 10, "percentage", "REF")
        code = PromoCode(
            promotion_id=promotion.id,
            code=_unique_code(db, "REF"),
            customer_id=customer.id,
            recipient_email=customer.email,
            recipient_first_name=customer.first_name,
            recipient_last_name=customer.last_name,
            max_uses=0,
        )
        db.add(code)
        db.flush()
        program.referral_code_id = code.id
        program.referral_code = code
        promotion.total_codes = (promotion.total_codes or 0) + 1

    if not code.email_sent and _valid_email(customer.email) and send_referral_code_email(customer.first_name, customer.email, code.code):
        code.email_sent = True
        code.email_sent_at = current
        code.email_subject = "Your Tag referral code"
        if promotion is None:
            promotion = db.query(Promotion).filter(Promotion.id == code.promotion_id).first()
        if promotion:
            promotion.codes_sent = (promotion.codes_sent or 0) + 1
    return code


def cancel_referral_code(db: Session, program: ReferralProgram, now: Optional[datetime] = None) -> PromoCode:
    code = db.query(PromoCode).filter(PromoCode.id == program.referral_code_id).first() if program.referral_code_id else None
    if not code:
        raise ValueError("Referral program does not have a referral code")

    current = now or _now()
    code.expires_at = current
    code.is_used = True
    code.used_at = code.used_at or current
    return code


def generate_replacement_referral_code(
    db: Session,
    program: ReferralProgram,
    now: Optional[datetime] = None,
) -> PromoCode:
    if program.referral_code_id:
        cancel_referral_code(db, program, now=now)
        program.referral_code_id = None
    program.status = PROGRAM_STATUS_OPTED_IN
    code = ensure_referral_code(db, program, now=now)
    if not code.email_sent:
        raise ValueError("Failed to send replacement referral code email")
    return code


def resend_referral_code(db: Session, program: ReferralProgram, now: Optional[datetime] = None) -> PromoCode:
    from email_service import send_referral_code_email

    code = db.query(PromoCode).filter(PromoCode.id == program.referral_code_id).first() if program.referral_code_id else None
    if not code:
        raise ValueError("Referral program does not have a referral code")
    if code.expires_at and code.expires_at <= (now or _now()):
        raise ValueError("Referral code is cancelled or expired")

    customer = program.customer or db.query(Customer).filter(Customer.id == program.customer_id).first()
    if not customer:
        raise ValueError("Referral program customer not found")
    if not _valid_email(customer.email):
        raise ValueError("Referral program customer does not have a valid email")

    current = now or _now()
    if not send_referral_code_email(customer.first_name, customer.email, code.code):
        raise ValueError("Failed to send referral code email")

    code.email_sent = True
    code.email_sent_at = current
    code.email_subject = "Your Tag referral code"
    return code


def ensure_reward_code(db: Session, program: ReferralProgram, now: Optional[datetime] = None) -> Optional[PromoCode]:
    if program.reward_code_id:
        return db.query(PromoCode).filter(PromoCode.id == program.reward_code_id).first()
    if not referral_rewards_enabled():
        return None

    from email_service import send_referral_reward_email

    customer = program.customer or db.query(Customer).filter(Customer.id == program.customer_id).first()
    if not customer:
        raise ValueError("Referral program customer not found")

    current = now or _now()
    promotion = _get_or_create_promotion(db, REWARD_PROMOTION_NAME, 100, "free_week", "RWD")
    code = PromoCode(
        promotion_id=promotion.id,
        code=_unique_code(db, "RWD"),
        customer_id=customer.id,
        recipient_email=customer.email,
        recipient_first_name=customer.first_name,
        recipient_last_name=customer.last_name,
        max_uses=None,
    )
    db.add(code)
    db.flush()
    program.reward_code_id = code.id
    program.reward_earned_at = program.reward_earned_at or current
    promotion.total_codes = (promotion.total_codes or 0) + 1

    if _valid_email(customer.email) and send_referral_reward_email(customer.first_name, customer.email, code.code):
        code.email_sent = True
        code.email_sent_at = current
        code.email_subject = "You earned a TAG referral reward"
        program.reward_email_sent_at = current
        promotion.codes_sent = (promotion.codes_sent or 0) + 1
    return code


def record_referral_attribution_for_booking(
    db: Session,
    booking: Optional[Booking],
    promo_code: Optional[PromoCode],
) -> Optional[ReferralAttribution]:
    if not booking or not promo_code:
        return None

    program = db.query(ReferralProgram).filter(ReferralProgram.referral_code_id == promo_code.id).first()
    if not program:
        return None

    existing = db.query(ReferralAttribution).filter(ReferralAttribution.booking_id == booking.id).first()
    if existing:
        return existing

    is_self_use = booking.customer_id == program.customer_id
    attribution = ReferralAttribution(
        referral_program_id=program.id,
        referrer_customer_id=program.customer_id,
        referred_customer_id=booking.customer_id,
        booking_id=booking.id,
        promo_code_id=promo_code.id,
        is_self_use=is_self_use,
        status=ATTRIBUTION_STATUS_DISQUALIFIED if is_self_use else ATTRIBUTION_STATUS_PENDING,
    )
    db.add(attribution)
    return attribution


def qualify_referral_for_booking(
    db: Session,
    booking: Optional[Booking],
    now: Optional[datetime] = None,
) -> Optional[ReferralAttribution]:
    if not booking:
        return None

    attribution = db.query(ReferralAttribution).filter(ReferralAttribution.booking_id == booking.id).first()
    if not attribution:
        return None

    if attribution.is_self_use:
        attribution.status = ATTRIBUTION_STATUS_DISQUALIFIED
        attribution.qualified_at = None
        program = attribution.program or db.query(ReferralProgram).filter(
            ReferralProgram.id == attribution.referral_program_id
        ).first()
        if program:
            recompute_referral_progress(db, program)
        return attribution

    if booking.status != BookingStatus.COMPLETED:
        return attribution

    current = now or _now()
    if attribution.status != ATTRIBUTION_STATUS_QUALIFIED:
        attribution.status = ATTRIBUTION_STATUS_QUALIFIED
        attribution.qualified_at = current

    program = attribution.program or db.query(ReferralProgram).filter(
        ReferralProgram.id == attribution.referral_program_id
    ).first()
    if not program:
        return attribution

    qualified_count = recompute_referral_progress(db, program)

    if qualified_count >= REFERRAL_REWARD_THRESHOLD and not program.reward_code_id:
        ensure_reward_code(db, program, now=current)
    return attribution
