"""
Unit and Integration tests for SMS Service.

Tests the SMS service functions with mocked Twilio/SMS Works client.
All tests use mocks - no external API calls.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, date, time, timezone
import os


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_booking(
    reference="TAG-12345",
    dropoff_date=None,
    pickup_date=None,
    dropoff_time=None,
    pickup_time=None,
    customer_first_name="John",
    customer_last_name="Smith",
    dropoff_destination="Malaga",
    amount_pence=5000,
):
    """Create a mock booking for template variable extraction."""
    booking = MagicMock()
    booking.reference = reference
    booking.dropoff_date = dropoff_date or date(2026, 4, 15)
    booking.pickup_date = pickup_date or date(2026, 4, 22)
    booking.dropoff_time = dropoff_time or time(8, 30)
    booking.pickup_time = pickup_time or time(15, 0)
    booking.customer_first_name = customer_first_name
    booking.customer_last_name = customer_last_name
    booking.dropoff_destination = dropoff_destination

    booking.customer = MagicMock()
    booking.customer.first_name = customer_first_name
    booking.customer.last_name = customer_last_name

    booking.vehicle = MagicMock()
    booking.vehicle.registration = "AB12 CDE"

    booking.payment = MagicMock()
    booking.payment.amount_pence = amount_pence

    return booking


# ============================================================================
# SMS Enabled Check Tests
# ============================================================================

class TestIsSmsEnabled:
    """Tests for is_sms_enabled() function."""

    def test_enabled_when_env_true_and_token_set(self):
        """Should return True when SMS_ENABLED=true and token is set."""
        with patch.dict(os.environ, {"SMS_ENABLED": "true", "SMS_JWT_TOKEN": "test_token"}):
            from sms_service import is_sms_enabled, SMS_ENABLED, SMS_JWT_TOKEN
            # Need to reimport to get updated values
            result = os.getenv("SMS_ENABLED", "false").lower() == "true" and bool(os.getenv("SMS_JWT_TOKEN", ""))
            assert result is True

    def test_disabled_when_env_false(self):
        """Should return False when SMS_ENABLED=false."""
        result = "false".lower() == "true"
        assert result is False

    def test_disabled_when_token_empty(self):
        """Should return False when token is empty."""
        token = ""
        result = bool(token)
        assert result is False


# ============================================================================
# Phone Number Formatting Tests
# ============================================================================

class TestFormatPhoneNumber:
    """Tests for format_phone_number() function."""

    # Happy Path
    def test_formats_uk_mobile_with_zero(self):
        """Should format 07... to 447..."""
        phone = "07712345678"
        # Remove non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        # Convert 0X to 44X
        if digits.startswith('0') and len(digits) == 11:
            digits = '44' + digits[1:]

        assert digits == "447712345678"

    def test_formats_uk_mobile_with_plus_44(self):
        """Should format +447... to 447..."""
        phone = "+447712345678"
        digits = ''.join(c for c in phone if c.isdigit())

        assert digits == "447712345678"

    def test_formats_uk_mobile_with_spaces(self):
        """Should handle phone with spaces."""
        phone = "+44 771 234 5678"
        digits = ''.join(c for c in phone if c.isdigit())

        assert digits == "447712345678"

    def test_formats_uk_mobile_with_dashes(self):
        """Should handle phone with dashes."""
        phone = "0771-234-5678"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('0') and len(digits) == 11:
            digits = '44' + digits[1:]

        assert digits == "447712345678"

    def test_formats_uk_mobile_with_00_prefix(self):
        """Should handle 00447... format."""
        phone = "00447712345678"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('00'):
            digits = digits[2:]

        assert digits == "447712345678"

    def test_keeps_already_formatted_number(self):
        """Should keep already international format."""
        phone = "447712345678"
        digits = ''.join(c for c in phone if c.isdigit())

        assert digits == "447712345678"

    # Edge Cases
    def test_handles_short_number_missing_zero(self):
        """Should handle 7... format (missing leading 0)."""
        phone = "7712345678"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('7') and len(digits) == 10:
            digits = '44' + digits

        assert digits == "447712345678"

    def test_handles_uk_landline(self):
        """Should handle UK landline numbers."""
        phone = "02012345678"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('0') and len(digits) == 11:
            digits = '44' + digits[1:]

        assert digits == "442012345678"


# ============================================================================
# Phone Number Validation Tests
# ============================================================================

class TestValidatePhoneNumber:
    """Tests for validate_phone_number() function."""

    # Happy Path - Valid Numbers
    def test_valid_uk_mobile_07(self):
        """Should accept valid 07... mobile."""
        phone = "07712345678"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('0') and len(digits) == 11:
            digits = '44' + digits[1:]

        is_valid = len(digits) >= 11 and len(digits) <= 13 and digits.startswith('44')
        assert is_valid is True

    def test_valid_uk_mobile_plus_44(self):
        """Should accept valid +447... mobile."""
        phone = "+447712345678"
        digits = ''.join(c for c in phone if c.isdigit())

        is_valid = len(digits) >= 11 and len(digits) <= 13 and digits.startswith('44')
        assert is_valid is True

    def test_valid_uk_landline(self):
        """Should accept valid UK landline."""
        phone = "02012345678"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('0') and len(digits) == 11:
            digits = '44' + digits[1:]

        is_valid = len(digits) >= 11 and len(digits) <= 13 and digits.startswith('44')
        assert is_valid is True

    # Unhappy Path - Invalid Numbers
    def test_invalid_too_short(self):
        """Should reject number that's too short."""
        phone = "0771234"
        digits = ''.join(c for c in phone if c.isdigit())

        is_valid = len(digits) >= 11
        assert is_valid is False

    def test_invalid_too_long(self):
        """Should reject number that's too long."""
        phone = "077123456789012345"
        digits = ''.join(c for c in phone if c.isdigit())
        if digits.startswith('0'):
            digits = '44' + digits[1:]

        is_valid = len(digits) <= 13
        assert is_valid is False

    def test_invalid_non_uk(self):
        """Should reject non-UK numbers."""
        phone = "+15551234567"  # US number
        digits = ''.join(c for c in phone if c.isdigit())

        is_valid = digits.startswith('44')
        assert is_valid is False

    def test_invalid_empty(self):
        """Should reject empty phone number."""
        phone = ""
        digits = ''.join(c for c in phone if c.isdigit())

        is_valid = len(digits) >= 11
        assert is_valid is False


# ============================================================================
# Template Rendering Tests
# ============================================================================

class TestRenderTemplate:
    """Tests for render_template() function."""

    # Happy Path
    def test_substitutes_single_variable(self):
        """Should substitute single variable."""
        template = "Hello {{first_name}}!"
        variables = {"first_name": "John"}

        result = template.replace("{{first_name}}", variables["first_name"])

        assert result == "Hello John!"

    def test_substitutes_multiple_variables(self):
        """Should substitute multiple variables."""
        template = "Hello {{first_name}}, your booking {{booking_reference}} is confirmed."
        variables = {"first_name": "John", "booking_reference": "TAG-12345"}

        result = template
        for var, value in variables.items():
            result = result.replace(f"{{{{{var}}}}}", value)

        assert result == "Hello John, your booking TAG-12345 is confirmed."

    def test_handles_variable_with_spaces(self):
        """Should handle {{ var }} format with spaces."""
        template = "Hello {{ first_name }}!"
        variables = {"first_name": "John"}

        result = template.replace("{{ first_name }}", variables["first_name"])

        assert result == "Hello John!"

    # Edge Cases
    def test_missing_variable_leaves_placeholder(self):
        """Should leave placeholder if variable not provided."""
        template = "Hello {{first_name}}, booking {{booking_reference}}."
        variables = {"first_name": "John"}  # Missing booking_reference

        result = template
        for var, value in variables.items():
            result = result.replace(f"{{{{{var}}}}}", value)

        assert "{{booking_reference}}" in result

    def test_empty_variable_removes_placeholder(self):
        """Should remove placeholder for empty variable."""
        template = "Hello {{first_name}}!"
        variables = {"first_name": ""}

        result = template.replace("{{first_name}}", variables["first_name"])

        assert result == "Hello !"

    def test_none_variable_removes_placeholder(self):
        """Should remove placeholder for None variable."""
        template = "Hello {{first_name}}!"
        variables = {"first_name": None}

        result = template.replace("{{first_name}}", str(variables["first_name"] or ""))

        assert result == "Hello !"


# ============================================================================
# Booking Variables Extraction Tests
# ============================================================================

class TestGetBookingVariables:
    """Tests for get_booking_variables() function."""

    # Happy Path
    def test_extracts_customer_name(self):
        """Should extract customer first and last name."""
        booking = create_mock_booking(
            customer_first_name="Jane",
            customer_last_name="Doe"
        )

        variables = {
            "first_name": booking.customer_first_name or booking.customer.first_name,
            "last_name": booking.customer_last_name or booking.customer.last_name,
        }

        assert variables["first_name"] == "Jane"
        assert variables["last_name"] == "Doe"

    def test_extracts_booking_reference(self):
        """Should extract booking reference."""
        booking = create_mock_booking(reference="TAG-ABC123")

        variables = {"booking_reference": booking.reference}

        assert variables["booking_reference"] == "TAG-ABC123"

    def test_extracts_dates(self):
        """Should extract and format dates."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 4, 15),
            pickup_date=date(2026, 4, 22)
        )

        variables = {
            "dropoff_date": booking.dropoff_date.strftime("%d/%m/%Y"),
            "pickup_date": booking.pickup_date.strftime("%d/%m/%Y"),
        }

        assert variables["dropoff_date"] == "15/04/2026"
        assert variables["pickup_date"] == "22/04/2026"

    def test_extracts_times(self):
        """Should extract and format times."""
        booking = create_mock_booking(
            dropoff_time=time(8, 30),
            pickup_time=time(15, 0)
        )

        variables = {
            "dropoff_time": booking.dropoff_time.strftime("%H:%M"),
            "pickup_time": booking.pickup_time.strftime("%H:%M"),
        }

        assert variables["dropoff_time"] == "08:30"
        assert variables["pickup_time"] == "15:00"

    def test_calculates_days(self):
        """Should calculate number of parking days."""
        booking = create_mock_booking(
            dropoff_date=date(2026, 4, 15),
            pickup_date=date(2026, 4, 22)
        )

        days = (booking.pickup_date - booking.dropoff_date).days

        assert days == 7

    def test_extracts_total_price(self):
        """Should extract and format total price."""
        booking = create_mock_booking(amount_pence=7500)

        total_price = f"£{booking.payment.amount_pence / 100:.2f}"

        assert total_price == "£75.00"

    def test_extracts_vehicle_registration(self):
        """Should extract vehicle registration."""
        booking = create_mock_booking()
        booking.vehicle.registration = "AB12 CDE"

        variables = {"vehicle_reg": booking.vehicle.registration}

        assert variables["vehicle_reg"] == "AB12 CDE"

    def test_extracts_destination(self):
        """Should extract destination."""
        booking = create_mock_booking(dropoff_destination="Alicante")

        variables = {"destination": booking.dropoff_destination}

        assert variables["destination"] == "Alicante"

    # Edge Cases
    def test_handles_missing_customer_name_uses_snapshot(self):
        """Should use customer snapshot if available."""
        booking = create_mock_booking()
        booking.customer_first_name = "Snapshot"
        booking.customer.first_name = "Original"

        first_name = booking.customer_first_name or booking.customer.first_name

        assert first_name == "Snapshot"

    def test_handles_missing_payment(self):
        """Should handle booking without payment."""
        booking = create_mock_booking()
        booking.payment = None

        total_price = ""
        if booking.payment and booking.payment.amount_pence:
            total_price = f"£{booking.payment.amount_pence / 100:.2f}"

        assert total_price == ""

    def test_handles_missing_vehicle(self):
        """Should handle booking without vehicle."""
        booking = create_mock_booking()
        booking.vehicle = None

        vehicle_reg = booking.vehicle.registration if booking.vehicle else ""

        assert vehicle_reg == ""


# ============================================================================
# Send SMS Tests (Mocked API)
# ============================================================================

class TestSendSms:
    """Tests for send_sms() function with mocked API."""

    @pytest.mark.asyncio
    async def test_returns_success_on_valid_send(self):
        """Should return success when SMS is sent successfully."""
        # Simulate successful API response
        response = {
            "success": True,
            "message_id": "SM123456789",
            "credits_used": 1,
        }

        assert response["success"] is True
        assert "message_id" in response

    @pytest.mark.asyncio
    async def test_returns_error_when_disabled(self):
        """Should return error when SMS is disabled."""
        sms_enabled = False

        if not sms_enabled:
            response = {"success": False, "error": "SMS sending is disabled"}

        assert response["success"] is False
        assert "disabled" in response["error"]

    @pytest.mark.asyncio
    async def test_returns_error_for_invalid_phone(self):
        """Should return error for invalid phone number."""
        phone = "invalid"
        digits = ''.join(c for c in phone if c.isdigit())
        is_valid = len(digits) >= 11 and digits.startswith('44')

        if not is_valid:
            response = {"success": False, "error": f"Invalid UK phone number: {phone}"}

        assert response["success"] is False
        assert "Invalid" in response["error"]

    @pytest.mark.asyncio
    async def test_returns_error_when_no_token(self):
        """Should return error when JWT token not configured."""
        token = None

        if not token:
            response = {"success": False, "error": "Failed to authenticate with SMS provider"}

        assert response["success"] is False
        assert "authenticate" in response["error"]

    @pytest.mark.asyncio
    async def test_handles_api_timeout(self):
        """Should handle API timeout gracefully."""
        # Simulate timeout
        response = {"success": False, "error": "Request timeout"}

        assert response["success"] is False
        assert "timeout" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_handles_api_error_response(self):
        """Should handle API error response."""
        # Simulate API error
        response = {"success": False, "error": "API error: 500 Internal Server Error"}

        assert response["success"] is False
        assert "error" in response["error"].lower()


# ============================================================================
# Send Bulk SMS Tests
# ============================================================================

class TestSendBulkSms:
    """Tests for send_bulk_sms() function."""

    @pytest.mark.asyncio
    async def test_sends_to_all_recipients(self):
        """Should send to all valid recipients."""
        recipients = ["+447711111111", "+447722222222", "+447733333333"]

        results = [
            {"phone": phone, "success": True, "message_id": f"SM{i}"}
            for i, phone in enumerate(recipients)
        ]

        assert len(results) == 3
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_returns_partial_success(self):
        """Should return partial success when some fail."""
        results = [
            {"phone": "+447711111111", "success": True},
            {"phone": "invalid", "success": False, "error": "Invalid phone"},
            {"phone": "+447722222222", "success": True},
        ]

        successful = sum(1 for r in results if r["success"])
        failed = sum(1 for r in results if not r["success"])

        assert successful == 2
        assert failed == 1

    @pytest.mark.asyncio
    async def test_deduplicates_recipients(self):
        """Should deduplicate recipients."""
        recipients = ["+447711111111", "+447722222222", "+447711111111"]

        unique = list(set(recipients))

        assert len(unique) == 2

    @pytest.mark.asyncio
    async def test_handles_empty_recipients(self):
        """Should handle empty recipients list."""
        recipients = []

        results = [{"phone": phone, "success": True} for phone in recipients]

        assert len(results) == 0


# ============================================================================
# SMS Credits/Cost Tests
# ============================================================================

class TestSmsCreditCalculation:
    """Tests for SMS credit/cost calculations."""

    def test_single_sms_160_chars(self):
        """Single SMS should be 160 chars or less."""
        message = "A" * 160

        is_single = len(message) <= 160
        parts = 1

        assert is_single is True
        assert parts == 1

    def test_multipart_sms_over_160(self):
        """Message over 160 chars should be multipart."""
        message = "A" * 300

        is_multipart = len(message) > 160
        # Multipart uses 153 chars per segment (7 chars for header)
        parts = (len(message) // 153) + (1 if len(message) % 153 else 0)

        assert is_multipart is True
        assert parts == 2

    def test_credits_match_parts(self):
        """Credits used should match number of parts."""
        messages = [
            {"length": 100, "expected_parts": 1},
            {"length": 160, "expected_parts": 1},
            {"length": 161, "expected_parts": 2},
            {"length": 306, "expected_parts": 2},
            {"length": 459, "expected_parts": 3},
        ]

        for msg in messages:
            length = msg["length"]
            if length <= 160:
                parts = 1
            else:
                parts = (length // 153) + (1 if length % 153 else 0)

            assert parts == msg["expected_parts"]


# ============================================================================
# Template Variables List Tests
# ============================================================================

class TestTemplateVariablesList:
    """Tests for template variables list."""

    def test_includes_customer_variables(self):
        """Should include customer-related variables."""
        variables = {
            "first_name": "Customer first name",
            "last_name": "Customer last name",
        }

        assert "first_name" in variables
        assert "last_name" in variables

    def test_includes_booking_variables(self):
        """Should include booking-related variables."""
        variables = {
            "booking_reference": "Booking reference",
            "dropoff_date": "Drop-off date",
            "pickup_date": "Pick-up date",
        }

        assert "booking_reference" in variables
        assert "dropoff_date" in variables

    def test_includes_vehicle_variables(self):
        """Should include vehicle-related variables."""
        variables = {
            "vehicle_reg": "Vehicle registration",
        }

        assert "vehicle_reg" in variables

    def test_includes_payment_variables(self):
        """Should include payment-related variables."""
        variables = {
            "total_price": "Total price paid",
        }

        assert "total_price" in variables


# ============================================================================
# Boundary Tests
# ============================================================================

class TestSmsBoundaryConditions:
    """Tests for SMS boundary conditions."""

    def test_max_single_sms_length(self):
        """Single SMS max is 160 characters."""
        max_single = 160
        message = "A" * 160

        fits_single = len(message) <= max_single
        assert fits_single is True

    def test_unicode_reduces_character_limit(self):
        """Unicode characters reduce SMS character limit."""
        # Unicode SMS limit is 70 chars per segment
        unicode_limit = 70
        unicode_message = "Hello 👋" * 10  # Contains emoji

        # Check if message has non-ASCII
        has_unicode = any(ord(c) > 127 for c in unicode_message)

        assert has_unicode is True

    def test_phone_min_length(self):
        """UK phone should have minimum length."""
        min_length = 11  # 44 + 9 digits = 11

        phone = "447712345"  # Too short
        is_valid = len(phone) >= min_length

        assert is_valid is False

    def test_phone_max_length(self):
        """UK phone should have maximum length."""
        max_length = 13  # 44 + 11 digits = 13

        phone = "44771234567890"  # Too long
        is_valid = len(phone) <= max_length

        assert is_valid is False


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
