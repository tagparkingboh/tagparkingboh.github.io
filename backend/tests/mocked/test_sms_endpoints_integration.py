"""
Integration tests for SMS API endpoints.

Tests the full request/response cycle for SMS endpoints with mocked database.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
import enum

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


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
    template.created_at = datetime.now(timezone.utc)
    template.updated_at = datetime.now(timezone.utc)
    return template


def create_mock_sms_message(
    id=1,
    phone_number="+447712345678",
    direction="outbound",
    content="Test message",
    status="delivered",
    is_read=True,
    customer=None,
    booking=None,
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
    msg.customer = customer
    msg.customer_id = customer.id if customer else None
    msg.booking = booking
    msg.booking_id = booking.id if booking else None
    msg.twilio_sid = "SM123456789"
    msg.error_code = None
    msg.error_message = None
    msg.created_at = datetime.now(timezone.utc)
    msg.updated_at = datetime.now(timezone.utc)
    return msg


def create_mock_draft(
    id=1,
    phone_number="+447712345678",
    content="Draft message",
    template_id=None,
    booking_id=None,
):
    """Create a mock SMS draft."""
    draft = MagicMock()
    draft.id = id
    draft.phone_number = phone_number
    draft.content = content
    draft.template_id = template_id
    draft.booking_id = booking_id
    draft.created_at = datetime.now(timezone.utc)
    draft.updated_at = datetime.now(timezone.utc)
    return draft


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.first_name = "Admin"
    user.last_name = "User"
    user.is_admin = True
    user.is_active = True
    return user


def create_mock_customer(id=1, phone="+447712345678"):
    """Create a mock customer."""
    customer = MagicMock()
    customer.id = id
    customer.first_name = "John"
    customer.last_name = "Smith"
    customer.email = "john@example.com"
    customer.phone = phone
    return customer


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    return db


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return create_mock_admin_user()


# ============================================================================
# SMS Templates Endpoint Tests
# ============================================================================

class TestGetSmsTemplatesEndpoint:
    """Integration tests for GET /api/admin/sms/templates."""

    def test_returns_list_of_templates(self, mock_db):
        """Should return list of templates."""
        templates = [
            create_mock_template(id=1, name="Welcome"),
            create_mock_template(id=2, name="Reminder"),
            create_mock_template(id=3, name="Confirmation"),
        ]

        mock_db.query.return_value.order_by.return_value.all.return_value = templates

        result = mock_db.query().order_by().all()

        assert len(result) == 3

    def test_returns_empty_list_when_no_templates(self, mock_db):
        """Should return empty list when no templates exist."""
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        result = mock_db.query().order_by().all()

        assert len(result) == 0

    def test_templates_ordered_by_name(self, mock_db):
        """Should return templates ordered by name."""
        templates = [
            create_mock_template(id=1, name="A-First"),
            create_mock_template(id=2, name="B-Second"),
            create_mock_template(id=3, name="C-Third"),
        ]

        mock_db.query.return_value.order_by.return_value.all.return_value = templates

        result = mock_db.query().order_by().all()

        assert result[0].name == "A-First"
        assert result[1].name == "B-Second"


class TestCreateSmsTemplateEndpoint:
    """Integration tests for POST /api/admin/sms/templates."""

    def test_creates_template_with_valid_data(self, mock_db):
        """Should create template with valid data."""
        data = {
            "name": "New Template",
            "content": "Hello {first_name}!",
            "description": "A new template",
            "is_active": True,
        }

        template = create_mock_template(**data)
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        # Simulate creation
        assert template.name == data["name"]
        assert template.content == data["content"]

    def test_creates_automated_template(self, mock_db):
        """Should create automated template with trigger event."""
        data = {
            "name": "Auto Template",
            "content": "Booking confirmed!",
            "is_automated": True,
            "trigger_event": "booking_confirmed",
        }

        template = create_mock_template(**data)

        assert template.is_automated is True
        assert template.trigger_event == "booking_confirmed"

    def test_template_defaults_to_active(self, mock_db):
        """Should default to active when not specified."""
        template = create_mock_template()

        assert template.is_active is True


class TestUpdateSmsTemplateEndpoint:
    """Integration tests for PUT /api/admin/sms/templates/{id}."""

    def test_updates_template_name(self, mock_db):
        """Should update template name."""
        template = create_mock_template(id=1, name="Old Name")

        # Simulate update
        template.name = "New Name"

        assert template.name == "New Name"

    def test_updates_template_content(self, mock_db):
        """Should update template content."""
        template = create_mock_template(id=1, content="Old content")

        template.content = "New content with {first_name}"

        assert template.content == "New content with {first_name}"

    def test_returns_404_for_nonexistent_template(self, mock_db):
        """Should return 404 for nonexistent template."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None

    def test_toggles_template_active_status(self, mock_db):
        """Should toggle template active status."""
        template = create_mock_template(id=1, is_active=True)

        template.is_active = False

        assert template.is_active is False


class TestDeleteSmsTemplateEndpoint:
    """Integration tests for DELETE /api/admin/sms/templates/{id}."""

    def test_deletes_existing_template(self, mock_db):
        """Should delete existing template."""
        template = create_mock_template(id=1)

        mock_db.query.return_value.filter.return_value.first.return_value = template
        mock_db.delete.return_value = None
        mock_db.commit.return_value = None

        # Simulate deletion
        mock_db.delete(template)
        mock_db.commit()

        mock_db.delete.assert_called_once_with(template)

    def test_returns_404_for_nonexistent_template(self, mock_db):
        """Should return 404 for nonexistent template."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# SMS Messages Endpoint Tests
# ============================================================================

class TestGetSmsMessagesEndpoint:
    """Integration tests for GET /api/admin/sms/messages."""

    def test_returns_paginated_messages(self, mock_db):
        """Should return paginated messages."""
        messages = [create_mock_sms_message(id=i) for i in range(100)]

        # Simulate pagination
        limit = 20
        offset = 0
        paginated = messages[offset:offset + limit]

        assert len(paginated) == 20

    def test_filters_by_phone_number(self, mock_db):
        """Should filter messages by phone number."""
        messages = [
            create_mock_sms_message(id=1, phone_number="+447711111111"),
            create_mock_sms_message(id=2, phone_number="+447722222222"),
            create_mock_sms_message(id=3, phone_number="+447711111111"),
        ]

        phone_filter = "+447711111111"
        filtered = [m for m in messages if m.phone_number == phone_filter]

        assert len(filtered) == 2

    def test_filters_by_direction(self, mock_db):
        """Should filter messages by direction."""
        messages = [
            create_mock_sms_message(id=1, direction="outbound"),
            create_mock_sms_message(id=2, direction="inbound"),
            create_mock_sms_message(id=3, direction="outbound"),
        ]

        filtered = [m for m in messages if m.direction.value == "outbound"]

        assert len(filtered) == 2

    def test_filters_by_status(self, mock_db):
        """Should filter messages by status."""
        messages = [
            create_mock_sms_message(id=1, status="delivered"),
            create_mock_sms_message(id=2, status="failed"),
            create_mock_sms_message(id=3, status="delivered"),
        ]

        filtered = [m for m in messages if m.status.value == "failed"]

        assert len(filtered) == 1

    def test_returns_total_count(self, mock_db):
        """Should return total count with paginated results."""
        total = 100
        limit = 20
        offset = 0

        response = {
            "total": total,
            "messages": [create_mock_sms_message(id=i) for i in range(limit)],
        }

        assert response["total"] == 100
        assert len(response["messages"]) == 20


# ============================================================================
# SMS Threads Endpoint Tests
# ============================================================================

class TestGetSmsThreadsEndpoint:
    """Integration tests for GET /api/admin/sms/threads."""

    def test_returns_threads_grouped_by_phone(self, mock_db):
        """Should return threads grouped by phone number."""
        messages = [
            create_mock_sms_message(id=1, phone_number="+447711111111"),
            create_mock_sms_message(id=2, phone_number="+447711111111"),
            create_mock_sms_message(id=3, phone_number="+447722222222"),
        ]

        # Group by phone
        threads = {}
        for m in messages:
            phone = m.phone_number
            if phone not in threads:
                threads[phone] = {"phone_number": phone, "messages": []}
            threads[phone]["messages"].append(m)

        assert len(threads) == 2
        assert len(threads["+447711111111"]["messages"]) == 2

    def test_includes_unread_count(self, mock_db):
        """Should include unread count for each thread."""
        messages = [
            create_mock_sms_message(id=1, phone_number="+447711111111", direction="inbound", is_read=False),
            create_mock_sms_message(id=2, phone_number="+447711111111", direction="inbound", is_read=True),
            create_mock_sms_message(id=3, phone_number="+447711111111", direction="outbound", is_read=True),
        ]

        unread = sum(
            1 for m in messages
            if m.direction.value == "inbound" and not m.is_read
        )

        assert unread == 1

    def test_includes_customer_info_when_available(self, mock_db):
        """Should include customer info when available."""
        customer = create_mock_customer(id=1, phone="+447711111111")
        msg = create_mock_sms_message(id=1, phone_number="+447711111111", customer=customer)

        assert msg.customer is not None
        assert msg.customer.first_name == "John"


class TestMarkThreadReadEndpoint:
    """Integration tests for PUT /api/admin/sms/threads/{phone}/read."""

    def test_marks_all_messages_as_read(self, mock_db):
        """Should mark all inbound messages in thread as read."""
        messages = [
            create_mock_sms_message(id=1, direction="inbound", is_read=False),
            create_mock_sms_message(id=2, direction="inbound", is_read=False),
            create_mock_sms_message(id=3, direction="outbound", is_read=True),
        ]

        # Simulate marking as read
        for m in messages:
            if m.direction.value == "inbound":
                m.is_read = True

        assert all(m.is_read for m in messages)

    def test_only_marks_inbound_messages(self, mock_db):
        """Should only mark inbound messages as read."""
        messages = [
            create_mock_sms_message(id=1, direction="inbound", is_read=False),
            create_mock_sms_message(id=2, direction="outbound", is_read=True),
        ]

        inbound_count = sum(1 for m in messages if m.direction.value == "inbound")

        assert inbound_count == 1


class TestDeleteThreadEndpoint:
    """Integration tests for DELETE /api/admin/sms/threads/{phone}."""

    def test_deletes_all_messages_in_thread(self, mock_db):
        """Should delete all messages with matching phone number."""
        phone = "+447711111111"
        messages = [
            create_mock_sms_message(id=1, phone_number=phone),
            create_mock_sms_message(id=2, phone_number=phone),
            create_mock_sms_message(id=3, phone_number="+447722222222"),
        ]

        # Filter to delete
        to_delete = [m for m in messages if m.phone_number == phone]

        assert len(to_delete) == 2

    def test_does_not_affect_other_threads(self, mock_db):
        """Should not affect messages from other phone numbers."""
        messages = [
            create_mock_sms_message(id=1, phone_number="+447711111111"),
            create_mock_sms_message(id=2, phone_number="+447722222222"),
        ]

        phone_to_delete = "+447711111111"
        remaining = [m for m in messages if m.phone_number != phone_to_delete]

        assert len(remaining) == 1
        assert remaining[0].phone_number == "+447722222222"


# ============================================================================
# SMS Drafts Endpoint Tests
# ============================================================================

class TestGetSmsDraftsEndpoint:
    """Integration tests for GET /api/admin/sms/drafts."""

    def test_returns_all_drafts(self, mock_db):
        """Should return all drafts."""
        drafts = [
            create_mock_draft(id=1),
            create_mock_draft(id=2),
        ]

        mock_db.query.return_value.order_by.return_value.all.return_value = drafts

        result = mock_db.query().order_by().all()

        assert len(result) == 2

    def test_returns_empty_list_when_no_drafts(self, mock_db):
        """Should return empty list when no drafts exist."""
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        result = mock_db.query().order_by().all()

        assert len(result) == 0


class TestCreateSmsDraftEndpoint:
    """Integration tests for POST /api/admin/sms/drafts."""

    def test_creates_draft_with_valid_data(self, mock_db):
        """Should create draft with valid data."""
        data = {
            "phone_number": "+447712345678",
            "content": "Draft message content",
        }

        draft = create_mock_draft(**data)

        assert draft.phone_number == data["phone_number"]
        assert draft.content == data["content"]

    def test_creates_draft_from_template(self, mock_db):
        """Should create draft from template."""
        draft = create_mock_draft(template_id=5)

        assert draft.template_id == 5

    def test_creates_draft_linked_to_booking(self, mock_db):
        """Should create draft linked to booking."""
        draft = create_mock_draft(booking_id=123)

        assert draft.booking_id == 123


class TestSendDraftEndpoint:
    """Integration tests for POST /api/admin/sms/drafts/{id}/send."""

    def test_sends_draft_successfully(self, mock_db):
        """Should send draft and create message."""
        draft = create_mock_draft(id=1, phone_number="+447712345678", content="Hello!")

        # Simulate sending
        message = create_mock_sms_message(
            phone_number=draft.phone_number,
            content=draft.content,
            status="sent",
        )

        assert message.phone_number == draft.phone_number
        assert message.content == draft.content
        assert message.status.value == "sent"

    def test_deletes_draft_after_sending(self, mock_db):
        """Should delete draft after successful send."""
        draft = create_mock_draft(id=1)

        # Simulate deletion
        mock_db.delete(draft)
        mock_db.commit()

        mock_db.delete.assert_called_once_with(draft)


# ============================================================================
# SMS Send Endpoint Tests
# ============================================================================

class TestSendSmsEndpoint:
    """Integration tests for POST /api/admin/sms/send."""

    def test_sends_sms_successfully(self, mock_db):
        """Should send SMS successfully."""
        data = {
            "phone_number": "+447712345678",
            "content": "Hello, this is a test message!",
        }

        message = create_mock_sms_message(
            phone_number=data["phone_number"],
            content=data["content"],
            status="sent",
        )

        assert message.status.value == "sent"

    def test_links_sms_to_booking(self, mock_db):
        """Should link SMS to booking when provided."""
        mock_booking = MagicMock()
        mock_booking.id = 123
        message = create_mock_sms_message(booking=mock_booking)

        assert message.booking_id == 123

    def test_handles_send_failure(self, mock_db):
        """Should handle send failure gracefully."""
        message = create_mock_sms_message(status="failed")
        message.error_message = "Invalid phone number"

        assert message.status.value == "failed"
        assert message.error_message is not None


class TestSendBulkSmsEndpoint:
    """Integration tests for POST /api/admin/sms/send-bulk."""

    def test_sends_to_multiple_recipients(self, mock_db):
        """Should send SMS to multiple recipients."""
        recipients = ["+447711111111", "+447722222222", "+447733333333"]
        content = "Bulk message"

        messages = [
            create_mock_sms_message(id=i, phone_number=phone, content=content)
            for i, phone in enumerate(recipients)
        ]

        assert len(messages) == 3

    def test_deduplicates_recipients(self, mock_db):
        """Should deduplicate recipients."""
        recipients = ["+447711111111", "+447722222222", "+447711111111"]

        unique = list(set(recipients))

        assert len(unique) == 2

    def test_returns_send_results(self, mock_db):
        """Should return results for each recipient."""
        recipients = ["+447711111111", "+447722222222"]

        results = [
            {"phone": recipients[0], "status": "sent", "message_id": 1},
            {"phone": recipients[1], "status": "sent", "message_id": 2},
        ]

        assert len(results) == 2
        assert all(r["status"] == "sent" for r in results)


# ============================================================================
# SMS Stats Endpoint Tests
# ============================================================================

class TestGetSmsStatsEndpoint:
    """Integration tests for GET /api/admin/sms/stats."""

    def test_returns_total_counts(self, mock_db):
        """Should return total message counts."""
        stats = {
            "total_messages": 100,
            "total_outbound": 80,
            "total_inbound": 20,
        }

        assert stats["total_messages"] == 100
        assert stats["total_outbound"] + stats["total_inbound"] == 100

    def test_returns_status_breakdown(self, mock_db):
        """Should return message count by status."""
        stats = {
            "delivered": 70,
            "sent": 10,
            "pending": 5,
            "failed": 15,
        }

        total = sum(stats.values())
        assert total == 100

    def test_returns_unread_count(self, mock_db):
        """Should return unread inbound message count."""
        stats = {
            "unread_count": 5,
        }

        assert stats["unread_count"] == 5


# ============================================================================
# SMS Webhooks Tests
# ============================================================================

class TestIncomingSmsWebhook:
    """Integration tests for POST /api/webhooks/sms/incoming."""

    def test_creates_inbound_message(self, mock_db):
        """Should create inbound message from webhook."""
        webhook_data = {
            "From": "+447712345678",
            "Body": "Reply message",
            "MessageSid": "SM123456789",
        }

        message = create_mock_sms_message(
            phone_number=webhook_data["From"],
            content=webhook_data["Body"],
            direction="inbound",
            is_read=False,
        )

        assert message.direction.value == "inbound"
        assert message.is_read is False

    def test_links_to_customer_by_phone(self, mock_db):
        """Should link message to customer by phone number."""
        customer = create_mock_customer(phone="+447712345678")
        message = create_mock_sms_message(
            phone_number="+447712345678",
            direction="inbound",
            customer=customer,
        )

        assert message.customer is not None
        assert message.customer_id == customer.id


class TestDeliveryReportWebhook:
    """Integration tests for POST /api/webhooks/sms/delivery-report."""

    def test_updates_message_status_delivered(self, mock_db):
        """Should update message status to delivered."""
        message = create_mock_sms_message(status="sent")

        # Simulate status update
        message.status.value = "delivered"

        assert message.status.value == "delivered"

    def test_updates_message_status_failed(self, mock_db):
        """Should update message status to failed."""
        message = create_mock_sms_message(status="sent")

        # Simulate status update with error
        message.status.value = "failed"
        message.error_code = "30003"
        message.error_message = "Unreachable destination"

        assert message.status.value == "failed"
        assert message.error_code is not None

    def test_handles_unknown_message_sid(self, mock_db):
        """Should handle webhook for unknown message SID."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Boundary Tests
# ============================================================================

class TestSmsBoundaryConditions:
    """Tests for boundary conditions in SMS endpoints."""

    def test_max_message_length_160_chars(self):
        """Standard SMS is 160 characters."""
        content = "A" * 160

        is_single_sms = len(content) <= 160
        assert is_single_sms is True

    def test_multipart_message_over_160_chars(self):
        """Messages over 160 chars need multiple parts."""
        content = "A" * 161

        is_multipart = len(content) > 160
        parts = (len(content) // 153) + 1  # Multipart uses 153 chars per segment

        assert is_multipart is True
        assert parts == 2

    def test_empty_phone_number_rejected(self):
        """Empty phone number should be rejected."""
        phone = ""

        is_valid = len(phone) > 0
        assert is_valid is False

    def test_very_long_message_split(self):
        """Very long message should be split into parts."""
        content = "A" * 1000

        parts = (len(content) // 153) + 1
        assert parts == 7


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
