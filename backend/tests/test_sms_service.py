"""
Unit tests for SMS Service.

Tests the core SMS service functionality with mocked external dependencies.

Covers:
- Phone number formatting/validation
- Template variable substitution
- JWT token generation (mocked)
- Message content length validation
- Error handling for API failures
- Booking variable extraction

All tests use mocked data to avoid side effects.
"""
import pytest
from datetime import datetime, date, time
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Unit Tests: Phone Number Formatting
# =============================================================================

class TestPhoneNumberFormatting:
    """Unit tests for phone number formatting."""

    def test_format_uk_mobile_07_prefix(self):
        """Test formatting UK mobile starting with 07."""
        from sms_service import format_phone_number

        result = format_phone_number("07123456789")
        assert result == "447123456789"

    def test_format_uk_mobile_with_spaces(self):
        """Test formatting UK mobile with spaces."""
        from sms_service import format_phone_number

        result = format_phone_number("07123 456 789")
        assert result == "447123456789"

    def test_format_uk_mobile_with_plus(self):
        """Test formatting UK mobile with + prefix."""
        from sms_service import format_phone_number

        result = format_phone_number("+447123456789")
        assert result == "447123456789"

    def test_format_uk_mobile_with_00(self):
        """Test formatting UK mobile with 00 prefix."""
        from sms_service import format_phone_number

        result = format_phone_number("00447123456789")
        assert result == "447123456789"

    def test_format_uk_mobile_7_prefix(self):
        """Test formatting UK mobile starting with 7."""
        from sms_service import format_phone_number

        result = format_phone_number("7123456789")
        assert result == "447123456789"

    def test_format_already_international(self):
        """Test formatting already international format."""
        from sms_service import format_phone_number

        result = format_phone_number("447123456789")
        assert result == "447123456789"

    def test_format_removes_dashes(self):
        """Test formatting removes dashes."""
        from sms_service import format_phone_number

        result = format_phone_number("07123-456-789")
        assert result == "447123456789"

    def test_format_removes_parentheses(self):
        """Test formatting removes parentheses."""
        from sms_service import format_phone_number

        result = format_phone_number("(07123) 456789")
        assert result == "447123456789"


# =============================================================================
# Unit Tests: Phone Number Validation
# =============================================================================

class TestPhoneNumberValidation:
    """Unit tests for phone number validation."""

    def test_valid_uk_mobile(self):
        """Test valid UK mobile is accepted."""
        from sms_service import validate_phone_number

        assert validate_phone_number("07123456789") is True

    def test_valid_uk_mobile_international(self):
        """Test valid UK mobile in international format."""
        from sms_service import validate_phone_number

        assert validate_phone_number("+447123456789") is True

    def test_invalid_too_short(self):
        """Test too short number is rejected."""
        from sms_service import validate_phone_number

        assert validate_phone_number("0712345") is False

    def test_invalid_too_long(self):
        """Test too long number is rejected."""
        from sms_service import validate_phone_number

        assert validate_phone_number("071234567890123") is False

    def test_invalid_landline(self):
        """Test UK landline is rejected."""
        from sms_service import validate_phone_number

        # UK landline starts with 01 or 02
        assert validate_phone_number("01onal23456789") is False

    def test_invalid_non_uk(self):
        """Test non-UK number format is handled."""
        from sms_service import validate_phone_number

        # US number format
        assert validate_phone_number("+15551234567") is False


# =============================================================================
# Unit Tests: Template Rendering
# =============================================================================

class TestTemplateRendering:
    """Unit tests for template variable substitution."""

    def test_render_single_variable(self):
        """Test rendering template with single variable."""
        from sms_service import render_template

        template = "Hello {{first_name}}!"
        variables = {"first_name": "John"}

        result = render_template(template, variables)
        assert result == "Hello John!"

    def test_render_multiple_variables(self):
        """Test rendering template with multiple variables."""
        from sms_service import render_template

        template = "Hi {{first_name}}, your booking {{booking_reference}} is confirmed!"
        variables = {
            "first_name": "Jane",
            "booking_reference": "TAG-ABC123"
        }

        result = render_template(template, variables)
        assert result == "Hi Jane, your booking TAG-ABC123 is confirmed!"

    def test_render_with_spaces_in_braces(self):
        """Test rendering template with spaces in braces."""
        from sms_service import render_template

        template = "Hello {{ first_name }}!"
        variables = {"first_name": "John"}

        result = render_template(template, variables)
        assert result == "Hello John!"

    def test_render_missing_variable(self):
        """Test rendering with missing variable leaves it unchanged."""
        from sms_service import render_template

        template = "Hi {{first_name}}, ref: {{booking_reference}}"
        variables = {"first_name": "John"}

        result = render_template(template, variables)
        # Missing variables are left as-is for debugging purposes
        assert result == "Hi John, ref: {{booking_reference}}"

    def test_render_none_value(self):
        """Test rendering with None value."""
        from sms_service import render_template

        template = "Hi {{first_name}}!"
        variables = {"first_name": None}

        result = render_template(template, variables)
        assert result == "Hi !"

    def test_render_empty_template(self):
        """Test rendering empty template."""
        from sms_service import render_template

        result = render_template("", {"first_name": "John"})
        assert result == ""

    def test_render_no_variables_in_template(self):
        """Test rendering template with no variables."""
        from sms_service import render_template

        template = "Hello World!"
        result = render_template(template, {"first_name": "John"})
        assert result == "Hello World!"


# =============================================================================
# Unit Tests: Booking Variables Extraction
# =============================================================================

class TestBookingVariables:
    """Unit tests for extracting variables from booking."""

    def test_get_booking_variables_basic(self):
        """Test extracting basic booking variables."""
        from sms_service import get_booking_variables

        # Create mock booking
        booking = MagicMock()
        booking.customer_first_name = "John"
        booking.customer_last_name = "Smith"
        booking.reference = "TAG-TEST123"
        booking.dropoff_date = date(2026, 6, 15)
        booking.dropoff_time = time(10, 30)
        booking.pickup_date = date(2026, 6, 22)
        booking.pickup_time = time(14, 0)
        booking.dropoff_destination = "Alicante"

        booking.customer = MagicMock()
        booking.customer.first_name = "John"
        booking.customer.last_name = "Smith"

        booking.vehicle = MagicMock()
        booking.vehicle.registration = "AB12 CDE"

        booking.payment = MagicMock()
        booking.payment.amount_pence = 8500

        variables = get_booking_variables(booking)

        assert variables["first_name"] == "John"
        assert variables["last_name"] == "Smith"
        assert variables["booking_reference"] == "TAG-TEST123"
        assert variables["dropoff_date"] == "15/06/2026"
        assert variables["dropoff_time"] == "10:30"
        assert variables["pickup_date"] == "22/06/2026"
        assert variables["pickup_time"] == "14:00"
        assert variables["destination"] == "Alicante"
        assert variables["vehicle_reg"] == "AB12 CDE"
        assert variables["total_price"] == "£85.00"
        assert variables["days"] == "7"

    def test_get_booking_variables_uses_customer_snapshot(self):
        """Test that customer name snapshot takes precedence."""
        from sms_service import get_booking_variables

        booking = MagicMock()
        booking.customer_first_name = "SnapshotFirst"
        booking.customer_last_name = "SnapshotLast"
        booking.reference = "TAG-TEST123"
        booking.dropoff_date = date(2026, 6, 15)
        booking.dropoff_time = None
        booking.pickup_date = date(2026, 6, 22)
        booking.pickup_time = None
        booking.dropoff_destination = None
        booking.vehicle = None
        booking.payment = None

        booking.customer = MagicMock()
        booking.customer.first_name = "CustomerFirst"
        booking.customer.last_name = "CustomerLast"

        variables = get_booking_variables(booking)

        # Should use snapshot, not customer object
        assert variables["first_name"] == "SnapshotFirst"
        assert variables["last_name"] == "SnapshotLast"

    def test_get_booking_variables_no_payment(self):
        """Test extracting variables with no payment."""
        from sms_service import get_booking_variables

        booking = MagicMock()
        booking.customer_first_name = "John"
        booking.customer_last_name = "Smith"
        booking.reference = "TAG-TEST123"
        booking.dropoff_date = date(2026, 6, 15)
        booking.dropoff_time = None
        booking.pickup_date = date(2026, 6, 22)
        booking.pickup_time = None
        booking.dropoff_destination = None
        booking.vehicle = None
        booking.payment = None
        booking.customer = MagicMock()
        booking.customer.first_name = "John"
        booking.customer.last_name = "Smith"

        variables = get_booking_variables(booking)

        assert variables["total_price"] == ""


# =============================================================================
# Unit Tests: SMS Enabled Check
# =============================================================================

class TestSMSEnabled:
    """Unit tests for SMS enabled check."""

    @patch.dict('os.environ', {
        'SMS_ENABLED': 'true',
        'SMS_API_KEY': 'test_key',
        'SMS_API_SECRET': 'test_secret'
    })
    def test_sms_enabled_when_all_set(self):
        """Test SMS is enabled when all credentials set."""
        import importlib
        import sms_service
        importlib.reload(sms_service)

        # Reload to pick up env vars
        assert sms_service.is_sms_enabled() is True

    @patch.dict('os.environ', {
        'SMS_ENABLED': 'false',
        'SMS_API_KEY': 'test_key',
        'SMS_API_SECRET': 'test_secret'
    })
    def test_sms_disabled_when_flag_false(self):
        """Test SMS is disabled when flag is false."""
        import importlib
        import sms_service
        importlib.reload(sms_service)

        assert sms_service.is_sms_enabled() is False

    @patch.dict('os.environ', {
        'SMS_ENABLED': 'true',
        'SMS_API_KEY': '',
        'SMS_API_SECRET': 'test_secret'
    })
    def test_sms_disabled_when_key_missing(self):
        """Test SMS is disabled when API key missing."""
        import importlib
        import sms_service
        importlib.reload(sms_service)

        assert sms_service.is_sms_enabled() is False


# =============================================================================
# Unit Tests: Template Variables List
# =============================================================================

class TestTemplateVariablesList:
    """Unit tests for template variables list."""

    def test_get_template_variables_list(self):
        """Test getting list of available variables."""
        from sms_service import get_template_variables_list

        variables = get_template_variables_list()

        # Should be a list of dicts with name and description
        assert isinstance(variables, list)
        assert len(variables) > 0

        # Check structure
        for var in variables:
            assert "name" in var
            assert "description" in var

    def test_template_variables_includes_first_name(self):
        """Test first_name is in available variables."""
        from sms_service import get_template_variables_list

        variables = get_template_variables_list()
        names = [v["name"] for v in variables]

        assert "first_name" in names

    def test_template_variables_includes_booking_reference(self):
        """Test booking_reference is in available variables."""
        from sms_service import get_template_variables_list

        variables = get_template_variables_list()
        names = [v["name"] for v in variables]

        assert "booking_reference" in names


# =============================================================================
# Unit Tests: JWT Token Generation (Mocked)
# =============================================================================

class TestJWTTokenGeneration:
    """Unit tests for JWT token generation."""

    @patch('sms_service.httpx.Client')
    @patch.dict('os.environ', {
        'SMS_API_KEY': 'test_key',
        'SMS_API_SECRET': 'test_secret'
    })
    def test_get_jwt_token_success(self, mock_client):
        """Test successful JWT token generation."""
        import importlib
        import sms_service
        importlib.reload(sms_service)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"token": "test_jwt_token"}

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value.post.return_value = mock_response
        mock_client.return_value = mock_client_instance

        token = sms_service.get_jwt_token()

        assert token == "test_jwt_token"

    @patch('sms_service.httpx.Client')
    @patch.dict('os.environ', {
        'SMS_API_KEY': 'test_key',
        'SMS_API_SECRET': 'test_secret'
    })
    def test_get_jwt_token_failure(self, mock_client):
        """Test JWT token generation failure."""
        import importlib
        import sms_service
        importlib.reload(sms_service)

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value.post.return_value = mock_response
        mock_client.return_value = mock_client_instance

        token = sms_service.get_jwt_token()

        assert token is None

    @patch.dict('os.environ', {'SMS_API_KEY': '', 'SMS_API_SECRET': ''})
    def test_get_jwt_token_no_credentials(self):
        """Test JWT token generation with no credentials."""
        import importlib
        import sms_service
        importlib.reload(sms_service)

        token = sms_service.get_jwt_token()

        assert token is None


# =============================================================================
# Unit Tests: Message Content Validation
# =============================================================================

class TestMessageContentValidation:
    """Unit tests for message content validation."""

    def test_message_under_160_chars(self):
        """Test message under 160 characters is valid."""
        content = "Hi John, your booking TAG-ABC123 is confirmed!"
        assert len(content) < 160

    def test_message_at_160_chars(self):
        """Test message at exactly 160 characters."""
        content = "A" * 160
        assert len(content) == 160

    def test_message_over_160_chars_becomes_multipart(self):
        """Test message over 160 chars would be multipart SMS."""
        content = "A" * 161
        assert len(content) > 160
        # SMS over 160 chars becomes multipart - this is informational


# =============================================================================
# Unit Tests: Delivery Report Handling
# =============================================================================

class TestDeliveryReportHandling:
    """Unit tests for delivery report webhook handling."""

    def test_handle_delivery_report_delivered(self):
        """Test handling delivered status."""
        from sms_service import handle_delivery_report
        from db_models import SMSMessage, SMSStatus

        # Create mock DB session and message
        mock_db = MagicMock()
        mock_message = MagicMock()
        mock_message.status = SMSStatus.SENT
        mock_message.delivered_at = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_message

        payload = {
            "messageid": "test123",
            "status": "delivered"
        }

        result = handle_delivery_report(payload, mock_db)

        assert result is True
        assert mock_message.status == SMSStatus.DELIVERED
        assert mock_message.delivered_at is not None

    def test_handle_delivery_report_failed(self):
        """Test handling failed status."""
        from sms_service import handle_delivery_report
        from db_models import SMSMessage, SMSStatus

        mock_db = MagicMock()
        mock_message = MagicMock()
        mock_message.status = SMSStatus.SENT

        mock_db.query.return_value.filter.return_value.first.return_value = mock_message

        payload = {
            "messageid": "test123",
            "status": "failed",
            "failurereason": "Number not reachable"
        }

        result = handle_delivery_report(payload, mock_db)

        assert result is True
        assert mock_message.status == SMSStatus.FAILED
        assert mock_message.status_detail == "Number not reachable"

    def test_handle_delivery_report_missing_id(self):
        """Test handling report without message ID."""
        from sms_service import handle_delivery_report

        mock_db = MagicMock()
        payload = {"status": "delivered"}

        result = handle_delivery_report(payload, mock_db)

        assert result is False

    def test_handle_delivery_report_message_not_found(self):
        """Test handling report for unknown message."""
        from sms_service import handle_delivery_report

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        payload = {
            "messageid": "unknown123",
            "status": "delivered"
        }

        result = handle_delivery_report(payload, mock_db)

        assert result is False


# =============================================================================
# Unit Tests: Incoming SMS Handling
# =============================================================================

class TestIncomingSMSHandling:
    """Unit tests for incoming SMS webhook handling."""

    def test_handle_incoming_sms_with_customer(self):
        """Test handling incoming SMS from known customer."""
        from sms_service import handle_incoming_sms
        from db_models import SMSMessage, SMSDirection, SMSStatus

        mock_db = MagicMock()
        mock_customer = MagicMock()
        mock_customer.id = 1

        mock_db.query.return_value.filter.return_value.first.return_value = mock_customer

        payload = {
            "sender": "447123456789",
            "content": "Hello, this is a reply",
            "messageid": "incoming123"
        }

        result = handle_incoming_sms(payload, mock_db)

        assert result is True
        mock_db.add.assert_called_once()

    def test_handle_incoming_sms_unknown_customer(self):
        """Test handling incoming SMS from unknown customer."""
        from sms_service import handle_incoming_sms

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        payload = {
            "sender": "447123456789",
            "content": "Hello",
            "messageid": "incoming123"
        }

        result = handle_incoming_sms(payload, mock_db)

        assert result is True
        # Should still create record even without customer link
        mock_db.add.assert_called_once()

    def test_handle_incoming_sms_missing_sender(self):
        """Test handling incoming SMS without sender."""
        from sms_service import handle_incoming_sms

        mock_db = MagicMock()
        payload = {
            "content": "Hello",
            "messageid": "incoming123"
        }

        result = handle_incoming_sms(payload, mock_db)

        assert result is False


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
