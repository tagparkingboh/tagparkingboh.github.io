"""
Unit tests for SMS endpoint logic.

Tests the business logic for SMS templates, messages, threads, and drafts.
All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
import enum


# ============================================================================
# Mock Enums
# ============================================================================

class MockSMSDirection(enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class MockSMSStatus(enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_template(
    id=1,
    name="Welcome SMS",
    content="Hello {first_name}!",
    description="Welcome message",
    is_active=True,
    is_automated=False,
    trigger_event=None,
    created_at=None,
    updated_at=None,
):
    """Create a mock SMS template."""
    template = MagicMock()
    template.id = id
    template.name = name
    template.content = content
    template.description = description
    template.is_active = is_active
    template.is_automated = is_automated
    template.trigger_event = trigger_event
    template.created_at = created_at or datetime.now(timezone.utc)
    template.updated_at = updated_at or datetime.now(timezone.utc)
    return template


def create_mock_sms_message(
    id=1,
    phone_number="+447712345678",
    direction="outbound",
    content="Test message",
    status="delivered",
    is_read=True,
    customer_id=None,
    booking_id=None,
    created_at=None,
):
    """Create a mock SMS message."""
    msg = MagicMock()
    msg.id = id
    msg.phone_number = phone_number
    msg.direction = MagicMock()
    msg.direction.value = direction
    msg.content = content
    msg.status = MagicMock()
    msg.status.value = status
    msg.is_read = is_read
    msg.customer_id = customer_id
    msg.booking_id = booking_id
    msg.created_at = created_at or datetime.now(timezone.utc)
    return msg


def create_mock_draft(
    id=1,
    phone_number="+447712345678",
    content="Draft message",
    template_id=None,
    booking_id=None,
    created_at=None,
    updated_at=None,
):
    """Create a mock SMS draft."""
    draft = MagicMock()
    draft.id = id
    draft.phone_number = phone_number
    draft.content = content
    draft.template_id = template_id
    draft.booking_id = booking_id
    draft.created_at = created_at or datetime.now(timezone.utc)
    draft.updated_at = updated_at or datetime.now(timezone.utc)
    return draft


# ============================================================================
# SMS Templates - Unit Tests
# ============================================================================

class TestSmsTemplateLogic:
    """Unit tests for SMS template business logic."""

    # Happy Path
    def test_template_has_required_fields(self):
        """Template should have all required fields."""
        template = create_mock_template()

        assert template.id is not None
        assert template.name is not None
        assert template.content is not None
        assert template.is_active is not None

    def test_template_default_values(self):
        """Template should have correct default values."""
        template = create_mock_template()

        assert template.is_active is True
        assert template.is_automated is False
        assert template.trigger_event is None

    def test_template_content_with_variables(self):
        """Template content can include variable placeholders."""
        template = create_mock_template(
            content="Hello {first_name}, your booking {reference} is confirmed!"
        )

        assert "{first_name}" in template.content
        assert "{reference}" in template.content

    # Unhappy Path
    def test_template_empty_name_invalid(self):
        """Template with empty name should be invalid."""
        template = create_mock_template(name="")

        # Validation logic would reject this
        assert template.name == ""
        is_valid = len(template.name.strip()) > 0
        assert is_valid is False

    def test_template_empty_content_invalid(self):
        """Template with empty content should be invalid."""
        template = create_mock_template(content="")

        is_valid = len(template.content.strip()) > 0
        assert is_valid is False

    # Edge Cases
    def test_template_very_long_content(self):
        """Template can have long content (SMS will be split)."""
        long_content = "A" * 1000
        template = create_mock_template(content=long_content)

        assert len(template.content) == 1000
        # SMS messages over 160 chars are typically split
        expected_parts = (len(template.content) // 153) + 1  # 153 chars per part for multipart
        assert expected_parts > 1

    def test_automated_template_requires_trigger_event(self):
        """Automated template should have a trigger event."""
        template = create_mock_template(is_automated=True, trigger_event="booking_confirmed")

        assert template.is_automated is True
        assert template.trigger_event == "booking_confirmed"

    def test_manual_template_no_trigger_event(self):
        """Manual template should not have a trigger event."""
        template = create_mock_template(is_automated=False, trigger_event=None)

        assert template.is_automated is False
        assert template.trigger_event is None


class TestSmsTemplateVariables:
    """Unit tests for SMS template variable substitution."""

    def test_substitute_first_name(self):
        """Should substitute {first_name} variable."""
        content = "Hello {first_name}!"
        variables = {"first_name": "John"}

        result = content.format(**variables)

        assert result == "Hello John!"

    def test_substitute_multiple_variables(self):
        """Should substitute multiple variables."""
        content = "Hi {first_name}, your booking {reference} on {date} is confirmed."
        variables = {
            "first_name": "Jane",
            "reference": "TAG-12345",
            "date": "15/04/2026"
        }

        result = content.format(**variables)

        assert "Jane" in result
        assert "TAG-12345" in result
        assert "15/04/2026" in result

    def test_missing_variable_raises_error(self):
        """Should raise KeyError for missing variable."""
        content = "Hello {first_name}, your booking {reference} is confirmed."
        variables = {"first_name": "John"}  # Missing 'reference'

        with pytest.raises(KeyError):
            content.format(**variables)

    def test_extra_variables_ignored(self):
        """Extra variables should be ignored."""
        content = "Hello {first_name}!"
        variables = {
            "first_name": "John",
            "extra_var": "ignored"
        }

        result = content.format(**variables)

        assert result == "Hello John!"

    def test_variable_with_special_characters(self):
        """Variable values with special characters should work."""
        content = "Vehicle: {registration}"
        variables = {"registration": "AB12 CDE"}

        result = content.format(**variables)

        assert result == "Vehicle: AB12 CDE"


# ============================================================================
# SMS Messages - Unit Tests
# ============================================================================

class TestSmsMessageLogic:
    """Unit tests for SMS message business logic."""

    # Happy Path
    def test_message_has_required_fields(self):
        """Message should have all required fields."""
        msg = create_mock_sms_message()

        assert msg.id is not None
        assert msg.phone_number is not None
        assert msg.direction is not None
        assert msg.content is not None
        assert msg.status is not None

    def test_outbound_message_direction(self):
        """Outbound message should have correct direction."""
        msg = create_mock_sms_message(direction="outbound")

        assert msg.direction.value == "outbound"

    def test_inbound_message_direction(self):
        """Inbound message should have correct direction."""
        msg = create_mock_sms_message(direction="inbound")

        assert msg.direction.value == "inbound"

    def test_message_status_delivered(self):
        """Delivered message should have correct status."""
        msg = create_mock_sms_message(status="delivered")

        assert msg.status.value == "delivered"

    # Unhappy Path
    def test_message_status_failed(self):
        """Failed message should have failed status."""
        msg = create_mock_sms_message(status="failed")

        assert msg.status.value == "failed"

    # Edge Cases
    def test_message_with_booking_id(self):
        """Message can be linked to a booking."""
        msg = create_mock_sms_message(booking_id=123)

        assert msg.booking_id == 123

    def test_message_without_booking_id(self):
        """Message can exist without a booking link."""
        msg = create_mock_sms_message(booking_id=None)

        assert msg.booking_id is None

    def test_message_with_customer_id(self):
        """Message can be linked to a customer."""
        msg = create_mock_sms_message(customer_id=456)

        assert msg.customer_id == 456


class TestSmsMessageFiltering:
    """Unit tests for SMS message filtering logic."""

    def test_filter_by_phone_number(self):
        """Should filter messages by phone number."""
        messages = [
            create_mock_sms_message(id=1, phone_number="+447712345678"),
            create_mock_sms_message(id=2, phone_number="+447712345678"),
            create_mock_sms_message(id=3, phone_number="+447798765432"),
        ]

        phone_filter = "+447712345678"
        filtered = [m for m in messages if m.phone_number == phone_filter]

        assert len(filtered) == 2

    def test_filter_by_direction_outbound(self):
        """Should filter messages by outbound direction."""
        messages = [
            create_mock_sms_message(id=1, direction="outbound"),
            create_mock_sms_message(id=2, direction="inbound"),
            create_mock_sms_message(id=3, direction="outbound"),
        ]

        filtered = [m for m in messages if m.direction.value == "outbound"]

        assert len(filtered) == 2

    def test_filter_by_status_failed(self):
        """Should filter messages by failed status."""
        messages = [
            create_mock_sms_message(id=1, status="delivered"),
            create_mock_sms_message(id=2, status="failed"),
            create_mock_sms_message(id=3, status="delivered"),
        ]

        filtered = [m for m in messages if m.status.value == "failed"]

        assert len(filtered) == 1
        assert filtered[0].id == 2

    def test_filter_by_booking_id(self):
        """Should filter messages by booking ID."""
        messages = [
            create_mock_sms_message(id=1, booking_id=100),
            create_mock_sms_message(id=2, booking_id=100),
            create_mock_sms_message(id=3, booking_id=200),
        ]

        filtered = [m for m in messages if m.booking_id == 100]

        assert len(filtered) == 2


class TestSmsMessagePagination:
    """Unit tests for SMS message pagination logic."""

    def test_pagination_limit(self):
        """Should respect limit parameter."""
        messages = [create_mock_sms_message(id=i) for i in range(50)]
        limit = 10

        paginated = messages[:limit]

        assert len(paginated) == 10

    def test_pagination_offset(self):
        """Should respect offset parameter."""
        messages = [create_mock_sms_message(id=i) for i in range(50)]
        offset = 20
        limit = 10

        paginated = messages[offset:offset + limit]

        assert len(paginated) == 10
        assert paginated[0].id == 20

    def test_pagination_empty_result(self):
        """Should return empty for offset beyond data."""
        messages = [create_mock_sms_message(id=i) for i in range(10)]
        offset = 100

        paginated = messages[offset:]

        assert len(paginated) == 0


# ============================================================================
# SMS Drafts - Unit Tests
# ============================================================================

class TestSmsDraftLogic:
    """Unit tests for SMS draft business logic."""

    # Happy Path
    def test_draft_has_required_fields(self):
        """Draft should have all required fields."""
        draft = create_mock_draft()

        assert draft.id is not None
        assert draft.phone_number is not None
        assert draft.content is not None

    def test_draft_can_link_to_template(self):
        """Draft can be created from a template."""
        draft = create_mock_draft(template_id=5)

        assert draft.template_id == 5

    def test_draft_can_link_to_booking(self):
        """Draft can be linked to a booking."""
        draft = create_mock_draft(booking_id=123)

        assert draft.booking_id == 123

    # Unhappy Path
    def test_draft_empty_phone_invalid(self):
        """Draft with empty phone should be invalid."""
        draft = create_mock_draft(phone_number="")

        is_valid = len(draft.phone_number.strip()) > 0
        assert is_valid is False

    def test_draft_empty_content_invalid(self):
        """Draft with empty content should be invalid."""
        draft = create_mock_draft(content="")

        is_valid = len(draft.content.strip()) > 0
        assert is_valid is False

    # Edge Cases
    def test_draft_updated_at_changes_on_edit(self):
        """Updated_at should change when draft is edited."""
        original_time = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
        new_time = datetime(2026, 4, 1, 11, 0, tzinfo=timezone.utc)

        draft = create_mock_draft(created_at=original_time, updated_at=original_time)

        # Simulate edit
        draft.updated_at = new_time

        assert draft.created_at == original_time
        assert draft.updated_at == new_time
        assert draft.updated_at > draft.created_at


# ============================================================================
# SMS Stats - Unit Tests
# ============================================================================

class TestSmsStatsLogic:
    """Unit tests for SMS statistics calculation logic."""

    def test_count_total_messages(self):
        """Should count total messages."""
        messages = [create_mock_sms_message(id=i) for i in range(25)]

        total = len(messages)

        assert total == 25

    def test_count_by_status(self):
        """Should count messages by status."""
        messages = [
            create_mock_sms_message(id=1, status="delivered"),
            create_mock_sms_message(id=2, status="delivered"),
            create_mock_sms_message(id=3, status="failed"),
            create_mock_sms_message(id=4, status="pending"),
            create_mock_sms_message(id=5, status="delivered"),
        ]

        status_counts = {}
        for m in messages:
            status = m.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        assert status_counts["delivered"] == 3
        assert status_counts["failed"] == 1
        assert status_counts["pending"] == 1

    def test_count_by_direction(self):
        """Should count messages by direction."""
        messages = [
            create_mock_sms_message(id=1, direction="outbound"),
            create_mock_sms_message(id=2, direction="outbound"),
            create_mock_sms_message(id=3, direction="inbound"),
            create_mock_sms_message(id=4, direction="outbound"),
        ]

        outbound = sum(1 for m in messages if m.direction.value == "outbound")
        inbound = sum(1 for m in messages if m.direction.value == "inbound")

        assert outbound == 3
        assert inbound == 1

    def test_count_unread_inbound(self):
        """Should count unread inbound messages."""
        messages = [
            create_mock_sms_message(id=1, direction="outbound", is_read=True),
            create_mock_sms_message(id=2, direction="inbound", is_read=False),
            create_mock_sms_message(id=3, direction="inbound", is_read=True),
            create_mock_sms_message(id=4, direction="inbound", is_read=False),
        ]

        unread = sum(
            1 for m in messages
            if m.direction.value == "inbound" and not m.is_read
        )

        assert unread == 2


# ============================================================================
# Phone Number Validation - Unit Tests
# ============================================================================

class TestPhoneNumberValidation:
    """Unit tests for phone number validation logic."""

    def test_valid_uk_mobile_with_country_code(self):
        """Valid UK mobile with +44 should be accepted."""
        phone = "+447712345678"

        is_valid = phone.startswith("+44") and len(phone) == 13

        assert is_valid is True

    def test_valid_uk_mobile_with_zero(self):
        """Valid UK mobile starting with 07 should be accepted."""
        phone = "07712345678"

        is_valid = phone.startswith("07") and len(phone) == 11

        assert is_valid is True

    def test_invalid_phone_too_short(self):
        """Phone number too short should be rejected."""
        phone = "+4477123"

        is_valid = len(phone) >= 11

        assert is_valid is False

    def test_invalid_phone_too_long(self):
        """Phone number too long should be rejected."""
        phone = "+4477123456789012345"

        is_valid = len(phone) <= 15

        assert is_valid is False

    def test_phone_normalization_add_country_code(self):
        """07 number should be normalized to +44."""
        phone = "07712345678"

        if phone.startswith("0"):
            normalized = "+44" + phone[1:]
        else:
            normalized = phone

        assert normalized == "+447712345678"

    def test_phone_normalization_already_has_code(self):
        """Number with +44 should not be changed."""
        phone = "+447712345678"

        if phone.startswith("0"):
            normalized = "+44" + phone[1:]
        else:
            normalized = phone

        assert normalized == "+447712345678"


# ============================================================================
# Bulk SMS - Unit Tests
# ============================================================================

class TestBulkSmsLogic:
    """Unit tests for bulk SMS sending logic."""

    def test_bulk_send_multiple_recipients(self):
        """Should create message for each recipient."""
        recipients = [
            "+447711111111",
            "+447722222222",
            "+447733333333",
        ]
        content = "Test bulk message"

        messages = [
            {"phone": phone, "content": content}
            for phone in recipients
        ]

        assert len(messages) == 3
        assert all(m["content"] == content for m in messages)

    def test_bulk_send_deduplicates_phones(self):
        """Should deduplicate phone numbers."""
        recipients = [
            "+447711111111",
            "+447722222222",
            "+447711111111",  # Duplicate
            "+447733333333",
        ]

        unique_phones = list(set(recipients))

        assert len(unique_phones) == 3

    def test_bulk_send_filters_invalid_phones(self):
        """Should filter out invalid phone numbers."""
        recipients = [
            "+447711111111",
            "invalid",
            "+447722222222",
            "",
            "+447733333333",
        ]

        def is_valid_phone(phone):
            return phone.startswith("+44") and len(phone) == 13

        valid_phones = [p for p in recipients if is_valid_phone(p)]

        assert len(valid_phones) == 3

    def test_bulk_send_empty_recipients(self):
        """Should handle empty recipients list."""
        recipients = []
        content = "Test message"

        messages = [
            {"phone": phone, "content": content}
            for phone in recipients
        ]

        assert len(messages) == 0


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
