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
    intent = stripe.PaymentIntent.create(
        amount=request.amount,
        currency=request.currency,
        automatic_payment_methods={"enabled": True},
        metadata={
            "booking_reference": request.booking_reference,
            "flight_number": request.flight_number,
            "flight_date": request.flight_date,
            "drop_off_date": request.drop_off_date,
            "pickup_date": request.pickup_date,
            "customer_name": request.customer_name,
            "departure_id": str(request.departure_id) if request.departure_id else "",
            "drop_off_slot": request.drop_off_slot or "",
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

    return PaymentStatus(
        payment_intent_id=intent.id,
        status=intent.status,
        amount=intent.amount,
        amount_received=intent.amount_received or 0,
        currency=intent.currency,
        customer_email=intent.receipt_email,
        booking_reference=intent.metadata.get("booking_reference"),
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


def calculate_price_in_pence(package: str, custom_price: Optional[float] = None) -> int:
    """
    Calculate the price in pence for Stripe.

    Args:
        package: "quick" (£99) or "longer" (£135)
        custom_price: Optional override price in pounds

    Returns:
        Price in pence
    """
    if custom_price is not None:
        return int(custom_price * 100)

    prices = {
        "quick": 9900,   # £99.00
        "longer": 13500,  # £135.00
    }

    return prices.get(package, 9900)
