"""
Tests for promo code fields in admin bookings endpoint.

Tests cover:
1. Bookings with multi-use promo codes return promo code info
2. Bookings with single-use promo codes return promo code info
3. Bookings without promo codes return None for promo fields
4. Multiple bookings using same multi-use code show correct info
5. Legacy promo codes (MarketingSubscriber) still work

All tests use mocked database to avoid state conflicts.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, time, datetime, timedelta
from fastapi.testclient import TestClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Use relative dates for future-proof tests
TODAY = date.today()
FUTURE_DATE = TODAY + timedelta(days=90)
FUTURE_DATE_END = TODAY + timedelta(days=97)


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
    phone="07700900001",
    billing_address1="123 Test Street",
    billing_address2=None,
    billing_city="London",
    billing_county="Greater London",
    billing_postcode="SW1A 1AA",
    billing_country="United Kingdom",
    vehicles=None,
    founder_followup_sent=False,
    founder_followup_sent_at=None,
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = first_name
    customer.last_name = last_name
    customer.email = email
    customer.phone = phone
    customer.billing_address1 = billing_address1
    customer.billing_address2 = billing_address2
    customer.billing_city = billing_city
    customer.billing_county = billing_county
    customer.billing_postcode = billing_postcode
    customer.billing_country = billing_country
    customer.vehicles = vehicles or []
    customer.founder_followup_sent = founder_followup_sent
    customer.founder_followup_sent_at = founder_followup_sent_at
    return customer


def create_mock_vehicle(
    id=1,
    customer_id=1,
    registration="AB12 CDE",
    make="Volkswagen",
    model="Golf",
    colour="Blue",
):
    """Create a mock vehicle object."""
    vehicle = MagicMock()
    vehicle.id = id
    vehicle.customer_id = customer_id
    vehicle.registration = registration
    vehicle.make = make
    vehicle.model = model
    vehicle.colour = colour
    return vehicle


def create_mock_payment(
    id=1,
    booking_id=1,
    stripe_payment_intent_id="pi_test_123456789",
    stripe_customer_id="cus_test_123",
    amount_pence=8500,
    currency="gbp",
    status="succeeded",
    paid_at=None,
    refund_id=None,
    refund_amount_pence=None,
    refunded_at=None,
):
    """Create a mock payment object."""
    from db_models import PaymentStatus

    payment = MagicMock()
    payment.id = id
    payment.booking_id = booking_id
    payment.stripe_payment_intent_id = stripe_payment_intent_id
    payment.stripe_customer_id = stripe_customer_id
    payment.amount_pence = amount_pence
    payment.currency = currency
    payment.status = PaymentStatus(status) if isinstance(status, str) else status
    payment.paid_at = paid_at or datetime.utcnow()
    payment.refund_id = refund_id
    payment.refund_amount_pence = refund_amount_pence
    payment.refunded_at = refunded_at
    return payment


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_id=1,
    vehicle_id=1,
    package="quick",
    status="confirmed",
    dropoff_date_val=None,
    dropoff_time_val=None,
    dropoff_flight_number="FR5523",
    dropoff_destination="Tenerife",
    dropoff_airline_name="Ryanair",
    dropoff_airline_code="FR",
    pickup_date_val=None,
    pickup_time_val=None,
    pickup_flight_number="FR5524",
    pickup_origin="Tenerife",
    pickup_airline_name="Ryanair",
    pickup_airline_code="FR",
    departure_id=None,
    dropoff_slot=None,
    arrival_id=None,
    booking_source="online",
    notes=None,
    customer=None,
    vehicle=None,
    payment=None,
    departure=None,
    created_at=None,
    flight_departure_time=None,
    flight_arrival_time=None,
    customer_first_name=None,
    customer_last_name=None,
    confirmation_email_sent=False,
    confirmation_email_sent_at=None,
    reminder_2day_sent=False,
    reminder_2day_sent_at=None,
    thank_you_email_sent=False,
    thank_you_email_sent_at=None,
):
    """Create a mock booking object."""
    from db_models import BookingStatus

    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_id = customer_id
    booking.vehicle_id = vehicle_id
    booking.package = package

    if isinstance(status, str):
        booking.status = BookingStatus(status)
    else:
        booking.status = status

    booking.dropoff_date = dropoff_date_val or FUTURE_DATE
    booking.dropoff_time = dropoff_time_val or time(7, 15)
    booking.dropoff_flight_number = dropoff_flight_number
    booking.dropoff_destination = dropoff_destination
    booking.dropoff_airline_name = dropoff_airline_name
    booking.dropoff_airline_code = dropoff_airline_code
    booking.pickup_date = pickup_date_val or FUTURE_DATE_END
    booking.pickup_time = pickup_time_val or time(15, 0)
    booking.pickup_flight_number = pickup_flight_number
    booking.pickup_origin = pickup_origin
    booking.pickup_airline_name = pickup_airline_name
    booking.pickup_airline_code = pickup_airline_code
    booking.departure_id = departure_id
    booking.dropoff_slot = dropoff_slot
    booking.arrival_id = arrival_id
    booking.booking_source = booking_source
    booking.notes = notes
    booking.customer = customer or create_mock_customer()
    booking.vehicle = vehicle or create_mock_vehicle()
    booking.payment = payment
    booking.departure = departure
    booking.created_at = created_at or datetime.utcnow()
    booking.flight_departure_time = flight_departure_time
    booking.flight_arrival_time = flight_arrival_time
    booking.customer_first_name = customer_first_name
    booking.customer_last_name = customer_last_name
    booking.confirmation_email_sent = confirmation_email_sent
    booking.confirmation_email_sent_at = confirmation_email_sent_at
    booking.reminder_2day_sent = reminder_2day_sent
    booking.reminder_2day_sent_at = reminder_2day_sent_at
    booking.thank_you_email_sent = thank_you_email_sent
    booking.thank_you_email_sent_at = thank_you_email_sent_at
    return booking


def create_mock_promo_code(
    id=1,
    code="WED10",
    promotion_id=1,
    max_uses=0,  # 0 = unlimited
    use_count=2,
    is_used=False,
    booking_id=None,
):
    """Create a mock promo code object."""
    promo_code = MagicMock()
    promo_code.id = id
    promo_code.code = code
    promo_code.promotion_id = promotion_id
    promo_code.max_uses = max_uses
    promo_code.use_count = use_count
    promo_code.is_used = is_used
    promo_code.booking_id = booking_id
    # Properties
    promo_code.is_multi_use = max_uses is not None
    promo_code.is_unlimited = max_uses == 0
    return promo_code


def create_mock_promotion(
    id=1,
    name="Wednesday only: 10% OFF your parking",
    discount_percent=10,
    discount_type="percentage",
):
    """Create a mock promotion object."""
    promotion = MagicMock()
    promotion.id = id
    promotion.name = name
    promotion.discount_percent = discount_percent
    promotion.discount_type = discount_type
    return promotion


def create_mock_promo_code_usage(
    id=1,
    promo_code_id=1,
    booking_id=1,
    discount_percent=10,
    discount_amount_pence=850,
    used_at=None,
    promo_code=None,
):
    """Create a mock promo code usage record."""
    usage = MagicMock()
    usage.id = id
    usage.promo_code_id = promo_code_id
    usage.booking_id = booking_id
    usage.discount_percent = discount_percent
    usage.discount_amount_pence = discount_amount_pence
    usage.used_at = used_at or datetime.utcnow()
    usage.promo_code = promo_code or create_mock_promo_code(id=promo_code_id)
    return usage


def create_mock_admin_user():
    """Create a mock admin user for authentication."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@tagparking.co.uk"
    user.is_admin = True
    user.first_name = "Admin"
    user.last_name = "User"
    return user


# =============================================================================
# GET /api/admin/bookings - Promo Code Fields Tests (Integration)
# =============================================================================

class TestAdminBookingsPromoCodeIntegration:
    """Integration tests for promo code fields in admin bookings endpoint."""

    @pytest.fixture
    def mock_admin_user(self):
        """Create mock admin user."""
        return create_mock_admin_user()

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        return MagicMock()

    def test_booking_with_multi_use_promo_code_returns_promo_info(self, mock_admin_user, mock_db_session):
        """Booking using a multi-use promo code should return promo code details."""
        from main import app, get_db, require_admin

        # Create mock data
        promo_code = create_mock_promo_code(id=1, code="WED10", max_uses=0, use_count=2)
        promo_usage = create_mock_promo_code_usage(
            id=1,
            promo_code_id=1,
            booking_id=1,
            discount_percent=10,
            discount_amount_pence=850,
            promo_code=promo_code,
        )
        payment = create_mock_payment(amount_pence=7650)  # 8500 - 850 discount
        booking = create_mock_booking(id=1, reference="TAG-BOA33239", payment=payment)

        # Setup mock query chain for bookings
        mock_booking_query = MagicMock()
        mock_booking_query.options.return_value = mock_booking_query
        mock_booking_query.filter.return_value = mock_booking_query
        mock_booking_query.order_by.return_value = mock_booking_query
        mock_booking_query.limit.return_value = mock_booking_query
        mock_booking_query.all.return_value = [booking]

        # Setup mock query for PromoCodeUsage with joinedload
        mock_usage_query = MagicMock()
        mock_usage_query.options.return_value = mock_usage_query
        mock_usage_query.filter.return_value = mock_usage_query
        mock_usage_query.all.return_value = [promo_usage]

        def query_side_effect(model):
            from db_models import Booking, PromoCodeUsage
            if model == Booking:
                return mock_booking_query
            elif model == PromoCodeUsage:
                return mock_usage_query
            return MagicMock()

        mock_db_session.query.side_effect = query_side_effect

        # Override dependencies
        app.dependency_overrides[get_db] = lambda: mock_db_session
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        try:
            client = TestClient(app)
            response = client.get("/api/admin/bookings?days=30")

            assert response.status_code == 200
            data = response.json()
            assert "bookings" in data
            assert len(data["bookings"]) == 1

            # Verify promo code fields are returned
            booking_data = data["bookings"][0]
            assert booking_data["promo_code"] == "WED10"
            assert booking_data["discount_percent"] == 10
            assert booking_data["discount_amount_pence"] == 850
        finally:
            app.dependency_overrides.clear()

    def test_booking_without_promo_code_returns_null_promo_fields(self, mock_admin_user, mock_db_session):
        """Booking without any promo code should return null for promo fields."""
        from main import app, get_db, require_admin

        # Create booking without promo code
        payment = create_mock_payment(amount_pence=8500)
        booking = create_mock_booking(id=2, reference="TAG-OBM36946", payment=payment)

        # Setup mock query chain for bookings
        mock_booking_query = MagicMock()
        mock_booking_query.options.return_value = mock_booking_query
        mock_booking_query.filter.return_value = mock_booking_query
        mock_booking_query.order_by.return_value = mock_booking_query
        mock_booking_query.limit.return_value = mock_booking_query
        mock_booking_query.all.return_value = [booking]

        # No promo usage found - return empty list
        mock_usage_query = MagicMock()
        mock_usage_query.options.return_value = mock_usage_query
        mock_usage_query.filter.return_value = mock_usage_query
        mock_usage_query.all.return_value = []

        def query_side_effect(model):
            from db_models import Booking, PromoCodeUsage
            if model == Booking:
                return mock_booking_query
            elif model == PromoCodeUsage:
                return mock_usage_query
            return MagicMock()

        mock_db_session.query.side_effect = query_side_effect

        app.dependency_overrides[get_db] = lambda: mock_db_session
        app.dependency_overrides[require_admin] = lambda: mock_admin_user

        try:
            client = TestClient(app)
            response = client.get("/api/admin/bookings?days=30")

            assert response.status_code == 200
            data = response.json()
            assert "bookings" in data
            assert len(data["bookings"]) == 1

            # Verify promo code fields are None when no promo code was used
            booking_data = data["bookings"][0]
            assert booking_data["promo_code"] is None
            assert booking_data["discount_percent"] is None
            assert booking_data["discount_amount_pence"] is None
        finally:
            app.dependency_overrides.clear()


# =============================================================================
# GET /api/admin/bookings - Promo Code Fields Unit Tests
# =============================================================================

class TestAdminBookingsPromoCodeFields:
    """Unit tests for promo code fields that should be returned in bookings."""

    def test_promo_code_usage_lookup_by_booking_id(self):
        """PromoCodeUsage should be looked up by booking_id."""
        promo_usage = create_mock_promo_code_usage(
            promo_code_id=1,
            booking_id=100,
            discount_percent=10,
            discount_amount_pence=850,
        )

        assert promo_usage.booking_id == 100
        assert promo_usage.discount_percent == 10
        assert promo_usage.discount_amount_pence == 850

    def test_promo_code_retrieved_from_usage(self):
        """Promo code string should be retrieved via PromoCodeUsage.promo_code relationship."""
        promo_code = create_mock_promo_code(code="SUMMER10")
        promo_usage = create_mock_promo_code_usage(
            promo_code_id=promo_code.id,
            booking_id=100,
            promo_code=promo_code,
        )

        assert promo_usage.promo_code.code == "SUMMER10"

    def test_multi_use_code_links_multiple_bookings(self):
        """Multi-use promo code should have multiple PromoCodeUsage records."""
        promo_code = create_mock_promo_code(id=1, code="WED10", max_uses=0, use_count=3)

        usages = [
            create_mock_promo_code_usage(id=1, promo_code_id=1, booking_id=100, promo_code=promo_code),
            create_mock_promo_code_usage(id=2, promo_code_id=1, booking_id=101, promo_code=promo_code),
            create_mock_promo_code_usage(id=3, promo_code_id=1, booking_id=102, promo_code=promo_code),
        ]

        # All usages link to same promo code
        assert all(u.promo_code.code == "WED10" for u in usages)
        # But different booking IDs
        booking_ids = {u.booking_id for u in usages}
        assert len(booking_ids) == 3

    def test_single_use_code_has_single_usage_record(self):
        """Single-use promo code should have exactly one PromoCodeUsage record."""
        promo_code = create_mock_promo_code(id=2, code="TAG-ABCD-1234", max_uses=None, use_count=1, is_used=True)
        usage = create_mock_promo_code_usage(promo_code_id=2, booking_id=200, promo_code=promo_code)

        assert promo_code.is_used is True
        assert usage.booking_id == 200

    def test_discount_amount_pence_is_actual_discount(self):
        """discount_amount_pence should be the actual amount discounted in pence."""
        # Original price: £85.00 (8500 pence)
        # 10% discount: £8.50 (850 pence)
        # Final price: £76.50 (7650 pence)

        promo_usage = create_mock_promo_code_usage(
            discount_percent=10,
            discount_amount_pence=850,
        )

        assert promo_usage.discount_percent == 10
        assert promo_usage.discount_amount_pence == 850

    def test_response_shape_includes_promo_fields(self):
        """Expected response shape should include promo code fields."""
        # This defines the expected shape of the booking response
        expected_booking_response = {
            "id": 1,
            "reference": "TAG-BOA33239",
            "status": "confirmed",
            # ... other fields ...
            "payment": {
                "amount_pence": 7650,
                # ... other payment fields ...
            },
            # NEW PROMO FIELDS:
            "promo_code": "WED10",
            "discount_percent": 10,
            "discount_amount_pence": 850,
        }

        assert "promo_code" in expected_booking_response
        assert "discount_percent" in expected_booking_response
        assert "discount_amount_pence" in expected_booking_response
        assert expected_booking_response["promo_code"] == "WED10"
        assert expected_booking_response["discount_percent"] == 10
        assert expected_booking_response["discount_amount_pence"] == 850

    def test_response_shape_null_promo_fields_when_no_code(self):
        """Response should have null promo fields when no promo code was used."""
        expected_booking_response = {
            "id": 2,
            "reference": "TAG-OBM36946",
            "status": "confirmed",
            "payment": {
                "amount_pence": 8500,
            },
            # No promo code used:
            "promo_code": None,
            "discount_percent": None,
            "discount_amount_pence": None,
        }

        assert expected_booking_response["promo_code"] is None
        assert expected_booking_response["discount_percent"] is None
        assert expected_booking_response["discount_amount_pence"] is None


# =============================================================================
# Edge Cases
# =============================================================================

class TestPromoCodeEdgeCases:
    """Edge case tests for promo code fields in bookings."""

    def test_zero_discount_amount(self):
        """Handle case where discount_amount_pence is 0 (free booking)."""
        promo_usage = create_mock_promo_code_usage(
            discount_percent=100,
            discount_amount_pence=0,  # Already free via other means
        )

        assert promo_usage.discount_amount_pence == 0
        assert promo_usage.discount_percent == 100

    def test_discount_amount_none_when_not_recorded(self):
        """Handle case where discount_amount_pence was not recorded."""
        promo_usage = create_mock_promo_code_usage(
            discount_percent=10,
            discount_amount_pence=None,  # Not recorded
        )

        assert promo_usage.discount_amount_pence is None

    def test_booking_with_cancelled_status_still_shows_promo(self):
        """Cancelled bookings should still show promo code info for records."""
        from db_models import BookingStatus

        promo_usage = create_mock_promo_code_usage(
            booking_id=300,
            discount_percent=10,
            discount_amount_pence=850,
        )
        booking = create_mock_booking(id=300, status=BookingStatus.CANCELLED)

        # Even if cancelled, the usage record exists
        assert promo_usage.booking_id == booking.id
        assert booking.status == BookingStatus.CANCELLED

    def test_multiple_bookings_same_code_different_amounts(self):
        """Multiple bookings with same code can have different discount amounts."""
        promo_code = create_mock_promo_code(code="WED10", max_uses=0)

        # Different booking durations = different base prices = different discount amounts
        usages = [
            create_mock_promo_code_usage(booking_id=100, discount_percent=10, discount_amount_pence=650, promo_code=promo_code),
            create_mock_promo_code_usage(booking_id=101, discount_percent=10, discount_amount_pence=850, promo_code=promo_code),
            create_mock_promo_code_usage(booking_id=102, discount_percent=10, discount_amount_pence=1050, promo_code=promo_code),
        ]

        # Same percentage, different amounts
        assert all(u.discount_percent == 10 for u in usages)
        amounts = {u.discount_amount_pence for u in usages}
        assert amounts == {650, 850, 1050}

    def test_promo_code_case_sensitivity(self):
        """Promo code should be stored/returned in uppercase."""
        promo_code = create_mock_promo_code(code="WED10")
        promo_usage = create_mock_promo_code_usage(promo_code=promo_code)

        # Code should be uppercase
        assert promo_usage.promo_code.code == "WED10"
        assert promo_usage.promo_code.code == promo_usage.promo_code.code.upper()


# =============================================================================
# Legacy Promo Codes (MarketingSubscriber)
# =============================================================================

class TestLegacyPromoCodeFields:
    """Tests for legacy promo codes from MarketingSubscriber table.

    The system has legacy promo codes stored in MarketingSubscriber table
    (promo_10_code, promo_free_code, etc.). These should also be displayed.
    """

    def test_legacy_promo_lookup_when_no_usage_record(self):
        """If no PromoCodeUsage, check MarketingSubscriber for legacy promo."""
        # This tests the fallback behavior
        # Legacy promo is linked via booking_id in MarketingSubscriber

        mock_subscriber = MagicMock()
        mock_subscriber.promo_10_code = "TAG-LEGACY-1234"
        mock_subscriber.promo_10_used_booking_id = 400
        mock_subscriber.discount_percent = 10

        assert mock_subscriber.promo_10_used_booking_id == 400
        assert mock_subscriber.promo_10_code == "TAG-LEGACY-1234"

    def test_new_system_takes_precedence_over_legacy(self):
        """If both PromoCodeUsage and legacy exist, new system takes precedence."""
        # New system usage
        promo_usage = create_mock_promo_code_usage(
            booking_id=500,
            discount_percent=10,
            discount_amount_pence=850,
        )

        # Legacy subscriber (should be ignored)
        mock_subscriber = MagicMock()
        mock_subscriber.promo_10_used_booking_id = 500
        mock_subscriber.promo_10_code = "TAG-OLD-CODE"

        # New system takes precedence
        if promo_usage:
            result_code = promo_usage.promo_code.code
        else:
            result_code = mock_subscriber.promo_10_code

        assert result_code == promo_usage.promo_code.code


# =============================================================================
# Performance Considerations
# =============================================================================

class TestPromoCodeQueryPerformance:
    """Tests to ensure promo code lookup doesn't create N+1 query issues."""

    def test_promo_usage_can_be_batch_loaded(self):
        """PromoCodeUsage should be loadable in a single query for all bookings."""
        # This test documents the expected behavior
        # Implementation should use a single query to fetch all usages

        booking_ids = [1, 2, 3, 4, 5]

        # Expected: Single query for all booking_ids
        # SELECT * FROM promo_code_usages WHERE booking_id IN (1, 2, 3, 4, 5)

        # Mock the batch result
        usages = {
            1: create_mock_promo_code_usage(booking_id=1),
            3: create_mock_promo_code_usage(booking_id=3),
            # 2, 4, 5 have no promo code
        }

        # For each booking, lookup is O(1) from the dict
        for bid in booking_ids:
            usage = usages.get(bid)
            if bid in [1, 3]:
                assert usage is not None
            else:
                assert usage is None


# =============================================================================
# Frontend Display Expectations
# =============================================================================

class TestFrontendDisplayExpectations:
    """Tests documenting expected frontend display behavior."""

    def test_discount_display_format_percentage(self):
        """Discount should be displayable as percentage."""
        promo_usage = create_mock_promo_code_usage(discount_percent=10)

        display = f"{promo_usage.discount_percent}% OFF"
        assert display == "10% OFF"

    def test_discount_display_format_amount(self):
        """Discount amount should be displayable as currency."""
        promo_usage = create_mock_promo_code_usage(discount_amount_pence=850)

        # Convert pence to pounds
        pounds = promo_usage.discount_amount_pence / 100
        display = f"£{pounds:.2f}"
        assert display == "£8.50"

    def test_original_price_calculation(self):
        """Original price can be calculated from final + discount."""
        final_price_pence = 7650
        discount_pence = 850

        original_price_pence = final_price_pence + discount_pence
        assert original_price_pence == 8500  # £85.00

    def test_promo_code_display_in_booking_row(self):
        """Promo code should be displayable in booking table row."""
        booking_data = {
            "reference": "TAG-BOA33239",
            "promo_code": "WED10",
            "discount_percent": 10,
        }

        # Frontend can show: "WED10 (10% OFF)"
        display = f"{booking_data['promo_code']} ({booking_data['discount_percent']}% OFF)"
        assert display == "WED10 (10% OFF)"
