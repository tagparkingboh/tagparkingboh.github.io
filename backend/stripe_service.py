"""
Stripe payment integration for TAG booking system.

Handles payment intents, webhooks, and payment confirmation.
"""
import stripe
from datetime import date, time
from typing import Optional
from pydantic import BaseModel

from config import get_settings, is_stripe_configured


# Initialize Stripe with API key
def init_stripe():
    """Initialize Stripe with the secret key."""
    settings = get_settings()
    if settings.stripe_secret_key:
        stripe.api_key = settings.stripe_secret_key


class PaymentIntentRequest(BaseModel):
    """Request to create a payment intent."""
    # Amount in pence (e.g., 9900 for £99.00)
    amount: int
    currency: str = "gbp"

    # Customer details for Stripe
    customer_email: str
    customer_name: str

    # Booking reference (stored in metadata)
    booking_reference: str

    # Flight details for metadata
    flight_number: str
    flight_date: str
    drop_off_date: str
    pickup_date: str

    # Slot booking details (for booking after payment succeeds)
    departure_id: Optional[int] = None
    drop_off_slot: Optional[str] = None

    # Promo code (if applied)
    promo_code: Optional[str] = None

    # Original amount before discount (in pence) - for email display
    original_amount: Optional[int] = None
    # Discount amount (in pence) - for email display
    discount_amount: Optional[int] = None

    # Airport quote conversion tracking
    airport_quote_snapshot_id: Optional[int] = None


class PaymentIntentResponse(BaseModel):
    """Response containing payment intent details."""
    client_secret: str
    payment_intent_id: str
    amount: int
    currency: str
    status: str


class PaymentStatus(BaseModel):
    """Payment status information."""
    payment_intent_id: str
    status: str
    amount: int
    amount_received: int
    currency: str
    customer_email: Optional[str] = None
    booking_reference: Optional[str] = None


def create_payment_intent(request: PaymentIntentRequest) -> PaymentIntentResponse:
    """
    Create a Stripe PaymentIntent for a booking.

    The PaymentIntent is created with metadata containing booking details,
    which will be used in the webhook to complete the booking.

    Args:
        request: Payment intent request with amount and booking details

    Returns:
        PaymentIntentResponse with client_secret for frontend

    Raises:
        stripe.error.StripeError: If Stripe API call fails
    """
    init_stripe()

    if not is_stripe_configured():
        raise ValueError("Stripe is not configured. Please set STRIPE_SECRET_KEY.")

    # Create the payment intent
    # Disable Link to avoid customer confusion - only allow card payments
    intent = stripe.PaymentIntent.create(
        amount=request.amount,
        currency=request.currency,
        payment_method_types=["card"],
        metadata={
            "booking_reference": request.booking_reference,
            "flight_number": request.flight_number,
            "flight_date": request.flight_date,
            "drop_off_date": request.drop_off_date,
            "pickup_date": request.pickup_date,
            "customer_name": request.customer_name,
            "departure_id": str(request.departure_id) if request.departure_id else "",
            "drop_off_slot": request.drop_off_slot or "",
            "promo_code": request.promo_code or "",
            "original_amount": str(request.original_amount) if request.original_amount else "",
            "discount_amount": str(request.discount_amount) if request.discount_amount else "",
            "airport_quote_snapshot_id": str(request.airport_quote_snapshot_id) if request.airport_quote_snapshot_id else "",
        },
        receipt_email=request.customer_email,
        description=f"TAG Parking - {request.flight_number} ({request.flight_date})",
    )

    return PaymentIntentResponse(
        client_secret=intent.client_secret,
        payment_intent_id=intent.id,
        amount=intent.amount,
        currency=intent.currency,
        status=intent.status,
    )


def get_payment_status(payment_intent_id: str) -> PaymentStatus:
    """
    Get the status of a payment intent.

    Args:
        payment_intent_id: The Stripe PaymentIntent ID

    Returns:
        PaymentStatus with current status
    """
    init_stripe()

    intent = stripe.PaymentIntent.retrieve(payment_intent_id)

    # Stripe metadata is a StripeObject, not a dict - use getattr instead of .get()
    metadata = getattr(intent, "metadata", None)
    booking_reference = getattr(metadata, "booking_reference", None) if metadata else None

    return PaymentStatus(
        payment_intent_id=intent.id,
        status=intent.status,
        amount=intent.amount,
        amount_received=intent.amount_received or 0,
        currency=intent.currency,
        customer_email=intent.receipt_email,
        booking_reference=booking_reference,
    )


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """
    Verify a Stripe webhook signature and return the event.

    Args:
        payload: Raw request body
        sig_header: Stripe-Signature header value

    Returns:
        The verified Stripe event

    Raises:
        stripe.error.SignatureVerificationError: If signature is invalid
    """
    init_stripe()
    settings = get_settings()

    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        settings.stripe_webhook_secret,
    )

    return event


def refund_payment(payment_intent_id: str, reason: str = "requested_by_customer") -> dict:
    """
    Refund a payment.

    Args:
        payment_intent_id: The PaymentIntent ID to refund
        reason: Reason for refund (requested_by_customer, duplicate, fraudulent)

    Returns:
        Refund details
    """
    init_stripe()

    refund = stripe.Refund.create(
        payment_intent=payment_intent_id,
        reason=reason,
    )

    return {
        "refund_id": refund.id,
        "status": refund.status,
        "amount": refund.amount,
    }


def lookup_refund(stripe_id: str) -> dict:
    """Resolve a refund id (re_...) or payment intent id (pi_...) pasted from
    the Stripe dashboard into canonical refund facts for the financials
    refund-sync edit.

    Returns the CUMULATIVE refunded amount from the charge (partial refunds
    accumulate on charge.amount_refunded), the payment intent so callers can
    back-fill it onto the Payment row, and a fully_refunded flag derived from
    the charge totals.

    Raises ValueError for unusable ids; Stripe API errors propagate.
    """
    init_stripe()
    stripe_id = (stripe_id or "").strip()

    if stripe_id.startswith("re_"):
        refund = stripe.Refund.retrieve(stripe_id)
    elif stripe_id.startswith("pi_"):
        refunds = stripe.Refund.list(payment_intent=stripe_id, limit=1)
        if not refunds.data:
            raise ValueError(f"No refunds found on payment intent {stripe_id}")
        refund = refunds.data[0]
    else:
        raise ValueError("Stripe id must start with re_ (refund) or pi_ (payment intent)")

    if refund.status != "succeeded":
        raise ValueError(f"Refund {refund.id} has status '{refund.status}', not succeeded")

    charge = None
    charge_id = getattr(refund, "charge", None)
    if charge_id:
        charge = stripe.Charge.retrieve(charge_id)

    total_refunded = charge.amount_refunded if charge is not None else refund.amount
    charge_amount = charge.amount if charge is not None else None

    return {
        "refund_id": refund.id,
        "payment_intent_id": getattr(refund, "payment_intent", None),
        "refund_amount_pence": total_refunded,
        "latest_refund_amount_pence": refund.amount,
        "charge_amount_pence": charge_amount,
        "reason": getattr(refund, "reason", None),
        "refunded_at_ts": getattr(refund, "created", None),
        "fully_refunded": bool(charge_amount and total_refunded >= charge_amount),
    }


def cancel_payment_intent(payment_intent_id: str) -> dict:
    """
    Cancel a PaymentIntent in Stripe.

    Used when cancelling a pending booking where payment was never completed.
    PaymentIntents can only be cancelled if they are not already succeeded.

    Args:
        payment_intent_id: The PaymentIntent ID to cancel

    Returns:
        Dict with cancellation status
    """
    init_stripe()

    try:
        intent = stripe.PaymentIntent.cancel(payment_intent_id)
        return {
            "success": True,
            "status": intent.status,
            "payment_intent_id": intent.id,
        }
    except stripe.error.InvalidRequestError as e:
        # PaymentIntent may already be succeeded, cancelled, or in an uncancellable state
        return {
            "success": False,
            "error": str(e),
        }


def calculate_price_in_pence(
    package: str = None,
    drop_off_date: Optional[date] = None,
    custom_price: Optional[float] = None,
    duration_days: Optional[int] = None,
    pickup_date: Optional[date] = None,
) -> int:
    """
    Calculate the price in pence for Stripe based on dynamic pricing.

    Args:
        package: "quick" (1 week) or "longer" (2 weeks) - legacy parameter
        drop_off_date: The drop-off date (used to determine advance booking tier)
        custom_price: Optional override price in pounds
        duration_days: Trip duration in days (1-14) - takes precedence over package
        pickup_date: Actual pickup date (pre-billing-cutoff) used for peak-day check

    Returns:
        Price in pence
    """
    if custom_price is not None:
        return int(custom_price * 100)

    # Use dynamic pricing from BookingService
    from booking_service import BookingService

    # Use flexible duration pricing if duration provided
    if duration_days is not None and drop_off_date:
        price = BookingService.calculate_price_for_duration(duration_days, drop_off_date, pickup_date)
    elif drop_off_date and package:
        # Legacy package-based pricing
        price = BookingService.calculate_price(package, drop_off_date)
    elif package:
        # Fallback to late tier prices if no date provided
        prices = BookingService.get_package_prices()
        price = prices.get(package, {}).get("late", 109.0)
    else:
        # Default fallback
        price = 99.0

    return int(price * 100)
