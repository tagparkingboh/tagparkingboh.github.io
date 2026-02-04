"""
Tests for the Booking Confirmation Email functionality.

Tests cover:
- Unit tests for send_booking_confirmation_email function
- Integration tests for email sending in the payment webhook
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, call
from httpx import AsyncClient, ASGITransport
from datetime import datetime, date, time

from main import app
from db_models import (
    Customer, Vehicle, Booking, Payment, FlightDeparture,
    BookingStatus, PaymentStatus
)
from email_service import send_booking_confirmation_email, send_email


# =============================================================================
# Test Database Setup - Use staging PostgreSQL via conftest
# =============================================================================

from sqlalchemy.orm import sessionmaker
from database import engine

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _cleanup_test_booking_data():
    """Helper to clean test booking data respecting FK constraints."""
    db = TestSessionLocal()
    try:
        # Delete in FK order: payments → bookings (don't delete customers/vehicles as they may be shared)
        db.query(Payment).filter(
            Payment.stripe_payment_intent_id.in_(['pi_test_123456', 'pi_test_2week'])
        ).delete(synchronize_session=False)
        db.query(Booking).filter(
            Booking.reference.in_(['TAG-TEST1234', 'TAG-2WEEK123'])
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def cleanup_test_booking_email_data():
    """Clean test data before and after each test."""
    _cleanup_test_booking_data()
    yield
    _cleanup_test_booking_data()


@pytest.fixture(scope="function")
def db():
    """Get a database session for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac


# =============================================================================
# Unit Tests for send_booking_confirmation_email
# =============================================================================

class TestSendBookingConfirmationEmail:
    """Unit tests for the send_booking_confirmation_email function."""

    @patch('email_service.send_email')
    def test_sends_email_with_correct_parameters(self, mock_send_email):
        """Test that the function calls send_email with correct parameters."""
        mock_send_email.return_value = True

        result = send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        assert result is True
        mock_send_email.assert_called_once()

        # Check the email was sent to the correct address
        call_args = mock_send_email.call_args
        assert call_args[0][0] == "test@example.com"
        assert "Booking Confirmed - TAG-12345678" in call_args[0][1]

    @patch('email_service.send_email')
    def test_email_contains_booking_reference(self, mock_send_email):
        """Test that the email HTML contains the booking reference."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-ABCD1234",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "TAG-ABCD1234" in html_content

    @patch('email_service.send_email')
    def test_email_contains_customer_name(self, mock_send_email):
        """Test that the email HTML contains the customer's first name."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="Sarah",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Hi Sarah" in html_content

    @patch('email_service.send_email')
    def test_email_contains_vehicle_details(self, mock_send_email):
        """Test that the email HTML contains vehicle details."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Volkswagen",
            vehicle_model="Golf",
            vehicle_colour="Silver",
            vehicle_registration="XY99 ZZZ",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Silver Volkswagen Golf" in html_content
        assert "XY99 ZZZ" in html_content

    @patch('email_service.send_email')
    def test_email_contains_flight_details(self, mock_send_email):
        """Test that the email HTML contains flight information."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="FR1234 to Malaga (AGP)",
            return_flight="FR1235 from Malaga (AGP)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "FR1234 to Malaga (AGP)" in html_content
        assert "FR1235 from Malaga (AGP)" in html_content

    @patch('email_service.send_email')
    def test_email_contains_dates_and_times(self, mock_send_email):
        """Test that the email HTML contains dates and times."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Monday, 15 January 2026",
            dropoff_time="08:30",
            pickup_date="Monday, 22 January 2026",
            pickup_time="From 16:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Monday, 15 January 2026" in html_content
        assert "08:30" in html_content
        assert "Monday, 22 January 2026" in html_content
        assert "From 16:45 onwards" in html_content

    @patch('email_service.send_email')
    def test_email_contains_payment_amount(self, mock_send_email):
        """Test that the email HTML contains the payment amount."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="2 Weeks",
            amount_paid="£150.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "£150.00" in html_content
        assert "2 Weeks" in html_content

    @patch('email_service.send_email')
    def test_email_with_promo_code_shows_discount(self, mock_send_email):
        """Test that promo code and discount are shown when provided."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£89.10",
            promo_code="TESTPROMO10",
            discount_amount="£9.90",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "TESTPROMO10" in html_content
        assert "£9.90" in html_content

    @patch('email_service.send_email')
    def test_email_without_promo_code_no_discount_section(self, mock_send_email):
        """Test that no discount section is shown when no promo code."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Promo Code" not in html_content

    @patch('email_service.send_email')
    def test_email_contains_important_information(self, mock_send_email):
        """Test that the email contains important arrival instructions."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "Short Stay Car Park" in html_content
        assert "booking reference ready" in html_content

    @patch('email_service.send_email')
    def test_email_contains_contact_information(self, mock_send_email):
        """Test that the email contains contact details."""
        mock_send_email.return_value = True

        send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        html_content = mock_send_email.call_args[0][2]
        assert "info@tagparking.co.uk" in html_content

    @patch('email_service.send_email')
    def test_returns_false_when_send_fails(self, mock_send_email):
        """Test that the function returns False when email sending fails."""
        mock_send_email.return_value = False

        result = send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        assert result is False


# =============================================================================
# Integration Tests for Email Sending in Webhook
# =============================================================================

class TestWebhookEmailIntegration:
    """Integration tests for email sending when payment succeeds."""

    def _create_test_booking(self, db, booking_reference="TAG-TEST1234"):
        """Helper to create a test booking with all related records."""
        # Get or create customer
        customer = db.query(Customer).filter(
            Customer.email == "john.doe@example.com"
        ).first()
        if not customer:
            customer = Customer(
                first_name="John",
                last_name="Doe",
                email="john.doe@example.com",
                phone="+447123456789",
            )
            db.add(customer)
            db.flush()
        else:
            customer.first_name = "John"
            customer.last_name = "Doe"
            customer.phone = "+447123456789"
            db.flush()

        # Get or create vehicle (update if exists to ensure test values)
        vehicle = db.query(Vehicle).filter(
            Vehicle.registration == "AB12 CDE",
            Vehicle.customer_id == customer.id,
        ).first()
        if not vehicle:
            vehicle = Vehicle(
                customer_id=customer.id,
                registration="AB12 CDE",
                make="Ford",
                model="Focus",
                colour="Blue",
            )
            db.add(vehicle)
        else:
            vehicle.make = "Ford"
            vehicle.model = "Focus"
            vehicle.colour = "Blue"
        db.flush()

        # Create booking
        booking = Booking(
            reference=booking_reference,
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="quick",
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 1, 15),
            dropoff_time=time(10, 15),
            dropoff_flight_number="TOM1234",
            dropoff_destination="Tenerife (TFS)",
            pickup_date=date(2026, 1, 22),
            pickup_time=time(14, 0),
            pickup_flight_number="TOM1235",
            pickup_origin="Tenerife (TFS)",
        )
        db.add(booking)
        db.flush()

        # Create payment record
        payment = Payment(
            booking_id=booking.id,
            stripe_payment_intent_id="pi_test_123456",
            amount_pence=9900,
            currency="gbp",
            status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()

        return booking

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_sends_confirmation_email_on_success(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that successful payment triggers confirmation email."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount": 9900,
                    "metadata": {
                        "booking_reference": booking.reference,
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "",
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        assert response.status_code == 200
        mock_send_email.assert_called_once()

        # Verify email parameters
        call_kwargs = mock_send_email.call_args[1]
        assert call_kwargs["email"] == "john.doe@example.com"
        assert call_kwargs["first_name"] == "John"
        assert call_kwargs["booking_reference"] == booking.reference
        assert "Ford" in call_kwargs["vehicle_make"]
        assert "Focus" in call_kwargs["vehicle_model"]

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_sends_email_with_promo_code(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that promo code info is included in confirmation email."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount": 8910,  # Discounted amount
                    "metadata": {
                        "booking_reference": booking.reference,
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "TESTPROMO10",
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        assert response.status_code == 200

        call_kwargs = mock_send_email.call_args[1]
        assert call_kwargs["promo_code"] == "TESTPROMO10"
        assert call_kwargs["discount_amount"] is not None

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_email_includes_correct_amount(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that the correct payment amount is included in email."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount": 15000,  # £150.00
                    "metadata": {
                        "booking_reference": booking.reference,
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "",
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        assert response.status_code == 200

        call_kwargs = mock_send_email.call_args[1]
        assert call_kwargs["amount_paid"] == "£150.00"

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_succeeds_even_if_email_fails(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that webhook returns success even if email sending fails."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount": 9900,
                    "metadata": {
                        "booking_reference": booking.reference,
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "",
                    }
                }
            }
        }

        # Simulate email sending failure
        mock_send_email.side_effect = Exception("SMTP connection failed")

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        # Webhook should still succeed (payment was processed)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_does_not_send_email_on_failed_payment(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that no email is sent when payment fails."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.payment_failed",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "metadata": {
                        "booking_reference": booking.reference,
                    },
                    "last_payment_error": {
                        "message": "Card declined"
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        # Email should NOT be sent for failed payments
        mock_send_email.assert_not_called()

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_formats_dates_correctly(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that dates are formatted nicely for the email."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount": 9900,
                    "metadata": {
                        "booking_reference": booking.reference,
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "",
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        assert response.status_code == 200

        call_kwargs = mock_send_email.call_args[1]
        # Check date is formatted like "Thursday, 15 January 2026"
        assert "January 2026" in call_kwargs["dropoff_date"]
        assert "January 2026" in call_kwargs["pickup_date"]

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_calculates_pickup_time(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that pickup time is calculated correctly (45 min after landing)."""
        booking = self._create_test_booking(db)

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_123456",
                    "amount": 9900,
                    "metadata": {
                        "booking_reference": booking.reference,
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "",
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        assert response.status_code == 200

        call_kwargs = mock_send_email.call_args[1]
        # Booking has pickup_time of 14:00, so pickup should be "From 14:45 onwards"
        assert call_kwargs["pickup_time"] == "From 14:45 onwards"

    @pytest.mark.asyncio
    @patch('main.send_booking_confirmation_email')
    @patch('main.verify_webhook_signature')
    async def test_webhook_handles_2_week_package(
        self, mock_verify, mock_send_email, client, db
    ):
        """Test that 2-week package is correctly identified."""
        # Get or create customer with "longer" package
        customer = db.query(Customer).filter(
            Customer.email == "jane@example.com"
        ).first()
        if not customer:
            customer = Customer(
                first_name="Jane",
                last_name="Smith",
                email="jane@example.com",
                phone="+447123456789",
            )
            db.add(customer)
            db.flush()

        vehicle = db.query(Vehicle).filter(
            Vehicle.registration == "XY99 ZZZ",
            Vehicle.customer_id == customer.id,
        ).first()
        if not vehicle:
            vehicle = Vehicle(
                customer_id=customer.id,
                registration="XY99 ZZZ",
                make="BMW",
                model="3 Series",
                colour="Black",
            )
            db.add(vehicle)
        else:
            vehicle.make = "BMW"
            vehicle.model = "3 Series"
            vehicle.colour = "Black"
        db.flush()

        booking = Booking(
            reference="TAG-2WEEK123",
            customer_id=customer.id,
            vehicle_id=vehicle.id,
            package="longer",  # 2-week package
            status=BookingStatus.PENDING,
            dropoff_date=date(2026, 1, 15),
            dropoff_time=time(10, 15),
            pickup_date=date(2026, 1, 29),
            pickup_time=time(14, 0),
        )
        db.add(booking)
        db.flush()

        payment = Payment(
            booking_id=booking.id,
            stripe_payment_intent_id="pi_test_2week",
            amount_pence=15000,
            currency="gbp",
            status=PaymentStatus.PENDING,
        )
        db.add(payment)
        db.commit()

        mock_verify.return_value = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_2week",
                    "amount": 15000,
                    "metadata": {
                        "booking_reference": "TAG-2WEEK123",
                        "departure_id": "",
                        "drop_off_slot": "",
                        "promo_code": "",
                    }
                }
            }
        }

        response = await client.post(
            "/api/webhooks/stripe",
            content=b"test payload",
            headers={"Stripe-Signature": "test_signature"}
        )

        assert response.status_code == 200

        call_kwargs = mock_send_email.call_args[1]
        assert call_kwargs["package_name"] == "2 Weeks"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEmailEdgeCases:
    """Tests for edge cases in email sending."""

    @patch('email_service.send_email')
    def test_handles_special_characters_in_name(self, mock_send_email):
        """Test that special characters in names are handled correctly."""
        mock_send_email.return_value = True

        result = send_booking_confirmation_email(
            email="test@example.com",
            first_name="José",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        assert result is True
        html_content = mock_send_email.call_args[0][2]
        assert "José" in html_content

    @patch('email_service.send_email')
    def test_handles_empty_optional_fields(self, mock_send_email):
        """Test that empty promo code fields don't cause issues."""
        mock_send_email.return_value = True

        result = send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Ford",
            vehicle_model="Focus",
            vehicle_colour="Blue",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
            promo_code=None,
            discount_amount=None,
        )

        assert result is True

    @patch('email_service.send_email')
    def test_handles_long_vehicle_details(self, mock_send_email):
        """Test handling of long vehicle make/model names."""
        mock_send_email.return_value = True

        result = send_booking_confirmation_email(
            email="test@example.com",
            first_name="John",
            booking_reference="TAG-12345678",
            dropoff_date="Saturday, 28 December 2025",
            dropoff_time="10:15",
            pickup_date="Saturday, 4 January 2026",
            pickup_time="From 14:45 onwards",
            departure_flight="TOM1234 to Tenerife (TFS)",
            return_flight="TOM1235 from Tenerife (TFS)",
            vehicle_make="Mercedes-Benz",
            vehicle_model="GLE 450 4MATIC SUV",
            vehicle_colour="Obsidian Black Metallic",
            vehicle_registration="AB12 CDE",
            package_name="1 Week",
            amount_paid="£99.00",
        )

        assert result is True
        html_content = mock_send_email.call_args[0][2]
        assert "Mercedes-Benz" in html_content
        assert "GLE 450 4MATIC SUV" in html_content
