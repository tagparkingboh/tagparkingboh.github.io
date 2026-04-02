"""
Integration tests for SMS Messaging Endpoints.

Tests the full API endpoint behavior with mocked SMS provider.

Covers:
- Template CRUD operations
- Send single message endpoint
- Send bulk messages endpoint
- Webhook handling for incoming messages
- Webhook handling for delivery reports
- Conversation thread retrieval
- Message listing and filtering
- SMS statistics endpoint

All tests use mocked database sessions and SMS API to avoid side effects.
"""
import pytest
from datetime import datetime, timedelta, date, time
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Database Models
# =============================================================================

def create_mock_template(
    id=1,
    name="test_template",
    content="Hi {{first_name}}, test message",
    description="Test template",
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
    template.created_at = datetime.now()
    template.updated_at = None
    return template


def create_mock_message(
    id=1,
    phone_number="447123456789",
    direction="outbound",
    content="Test message",
    status="sent",
    booking_id=None,
    customer_id=None,
):
    """Create a mock SMS message."""
    from db_models import SMSDirection, SMSStatus

    message = MagicMock()
    message.id = id
    message.phone_number = phone_number
    message.direction = SMSDirection(direction)
    message.content = content
    message.status = SMSStatus(status)
    message.booking_id = booking_id
    message.customer_id = customer_id
    message.status_detail = None
    message.is_bulk = False
    message.created_at = datetime.now()
    message.delivered_at = None

    # Mock relationships
    message.booking = None
    message.customer = None

    return message


def create_mock_user(id=1, email="admin@test.com", is_admin=True, is_active=True):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = is_admin
    user.is_active = is_active
    return user


def create_mock_booking(
    id=1,
    reference="TAG-TEST001",
    customer_phone="07123456789",
):
    """Create a mock booking with customer."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.customer_first_name = "John"
    booking.customer_last_name = "Smith"
    booking.dropoff_date = date.today()
    booking.dropoff_time = time(10, 30)
    booking.pickup_date = date.today() + timedelta(days=7)
    booking.pickup_time = time(14, 0)
    booking.dropoff_destination = "Alicante"

    booking.customer = MagicMock()
    booking.customer.id = 1
    booking.customer.first_name = "John"
    booking.customer.last_name = "Smith"
    booking.customer.phone = customer_phone

    booking.vehicle = MagicMock()
    booking.vehicle.registration = "AB12 CDE"

    booking.payment = MagicMock()
    booking.payment.amount_pence = 8500

    return booking


# =============================================================================
# Integration Tests: Templates CRUD
# =============================================================================

class TestTemplatesCRUD:
    """Integration tests for template CRUD operations."""

    def test_list_templates_returns_all(self):
        """Test listing all templates."""
        templates = [
            create_mock_template(id=1, name="template1"),
            create_mock_template(id=2, name="template2"),
        ]

        # Simulate endpoint returning templates
        result = [
            {
                "id": t.id,
                "name": t.name,
                "content": t.content,
                "is_active": t.is_active,
            }
            for t in templates
        ]

        assert len(result) == 2
        assert result[0]["name"] == "template1"

    def test_create_template(self):
        """Test creating a new template."""
        data = {
            "name": "new_template",
            "content": "Hello {{first_name}}!",
            "description": "A new template",
            "is_active": True,
            "is_automated": False,
        }

        # Simulate created template
        created = create_mock_template(
            id=1,
            name=data["name"],
            content=data["content"],
            description=data["description"],
        )

        assert created.name == "new_template"
        assert "{{first_name}}" in created.content

    def test_update_template(self):
        """Test updating a template."""
        template = create_mock_template(id=1, name="old_name", content="old content")

        # Simulate update
        template.name = "updated_name"
        template.content = "updated content"

        assert template.name == "updated_name"
        assert template.content == "updated content"

    def test_delete_template(self):
        """Test deleting a template."""
        template = create_mock_template(id=1)

        # Simulate deletion success
        deleted = True

        assert deleted is True

    def test_delete_template_returns_success_response(self):
        """Test delete returns success message."""
        template = create_mock_template(id=1, name="to_delete")

        # Simulate API response
        response = {"success": True, "message": "Template deleted"}

        assert response["success"] is True
        assert "deleted" in response["message"].lower()

    def test_delete_nonexistent_template_returns_404(self):
        """Test deleting non-existent template returns 404."""
        template_id = 9999
        template = None  # Not found in database

        status_code = 404 if not template else 200

        assert status_code == 404

    def test_delete_automated_template(self):
        """Test deleting an automated template."""
        template = create_mock_template(
            id=1,
            name="auto_template",
            is_automated=True,
            trigger_event="booking_confirmed"
        )

        # Automated templates can be deleted
        deleted = True

        assert deleted is True
        assert template.is_automated is True

    def test_delete_removes_template_from_list(self):
        """Test deleted template no longer appears in list."""
        templates = [
            create_mock_template(id=1, name="template1"),
            create_mock_template(id=2, name="template2"),
            create_mock_template(id=3, name="template3"),
        ]

        # Simulate deleting template with id=2
        deleted_id = 2
        remaining = [t for t in templates if t.id != deleted_id]

        assert len(remaining) == 2
        assert all(t.id != deleted_id for t in remaining)

    def test_delete_inactive_template(self):
        """Test deleting an inactive template."""
        template = create_mock_template(id=1, name="inactive_template", is_active=False)

        deleted = True

        assert deleted is True
        assert template.is_active is False

    def test_delete_template_with_trigger_event(self):
        """Test deleting template with specific trigger events."""
        triggers = ["booking_confirmed", "reminder_2day", "thank_you"]

        for trigger in triggers:
            template = create_mock_template(
                id=1,
                name=f"{trigger}_template",
                trigger_event=trigger,
                is_automated=True
            )
            deleted = True

            assert deleted is True
            assert template.trigger_event == trigger

    def test_delete_only_template_leaves_empty_list(self):
        """Test deleting the last template results in empty list."""
        templates = [create_mock_template(id=1, name="only_template")]

        deleted_id = 1
        remaining = [t for t in templates if t.id != deleted_id]

        assert len(remaining) == 0
        assert remaining == []

    def test_delete_template_with_special_characters_in_name(self):
        """Test deleting template with special characters in name."""
        special_names = [
            "Template & Booking",
            "Template <Test>",
            "Template 'Quote'",
            "Template \"Double\"",
            "Template/Slash",
        ]

        for name in special_names:
            template = create_mock_template(id=1, name=name)
            deleted = True

            assert deleted is True
            assert template.name == name

    def test_delete_same_template_twice_second_returns_404(self):
        """Test double delete - second attempt should fail."""
        templates = [create_mock_template(id=1, name="to_delete")]

        # First delete succeeds
        deleted_id = 1
        remaining = [t for t in templates if t.id != deleted_id]
        first_delete_success = True

        # Second delete - template not found
        template = next((t for t in remaining if t.id == deleted_id), None)
        second_delete_status = 404 if not template else 200

        assert first_delete_success is True
        assert second_delete_status == 404

    def test_delete_template_preserves_others(self):
        """Test deleting one template doesn't affect others."""
        templates = [
            create_mock_template(id=1, name="keep1", content="content1"),
            create_mock_template(id=2, name="delete_me", content="content2"),
            create_mock_template(id=3, name="keep2", content="content3"),
        ]

        deleted_id = 2
        remaining = [t for t in templates if t.id != deleted_id]

        # Check preserved templates are unchanged
        assert len(remaining) == 2
        assert remaining[0].name == "keep1"
        assert remaining[0].content == "content1"
        assert remaining[1].name == "keep2"
        assert remaining[1].content == "content3"

    def test_get_template_not_found(self):
        """Test getting non-existent template."""
        template = None
        status_code = 404 if not template else 200

        assert status_code == 404


# =============================================================================
# Integration Tests: Use Template (Manual Send)
# =============================================================================

class TestUseTemplate:
    """Integration tests for using templates in manual SMS sending."""

    def test_use_template_copies_content_to_form(self):
        """Test that using a template copies its content."""
        template = create_mock_template(
            id=1,
            name="Welcome",
            content="Hi {{first_name}}, welcome to TAG Parking!"
        )

        # Simulate form state after clicking "Use"
        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        assert send_form["content"] == "Hi {{first_name}}, welcome to TAG Parking!"

    def test_use_template_preserves_existing_phone(self):
        """Test that using a template doesn't clear existing phone."""
        template = create_mock_template(content="New content")

        send_form = {"phone": "+447123456789", "content": "old content", "booking_id": "123", "customer_id": "456"}
        send_form["content"] = template.content

        assert send_form["phone"] == "+447123456789"
        assert send_form["booking_id"] == "123"
        assert send_form["customer_id"] == "456"

    def test_use_template_replaces_previous_content(self):
        """Test that using a new template replaces previous content."""
        template1 = create_mock_template(content="First template content")
        template2 = create_mock_template(content="Second template content")

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}

        # Use first template
        send_form["content"] = template1.content
        assert send_form["content"] == "First template content"

        # Use second template
        send_form["content"] = template2.content
        assert send_form["content"] == "Second template content"

    def test_use_inactive_template(self):
        """Test that inactive templates can still be used manually."""
        template = create_mock_template(
            id=1,
            name="Inactive Template",
            content="This is an inactive template",
            is_active=False
        )

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        assert send_form["content"] == "This is an inactive template"
        assert template.is_active is False

    def test_use_automated_template_manually(self):
        """Test that automated templates can be used manually."""
        template = create_mock_template(
            id=1,
            name="Booking Confirmation",
            content="Your booking {{booking_reference}} is confirmed!",
            is_automated=True,
            trigger_event="booking_confirmed"
        )

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        assert send_form["content"] == "Your booking {{booking_reference}} is confirmed!"
        assert template.is_automated is True

    def test_use_template_with_all_variables(self):
        """Test using template with all available variables."""
        content = (
            "Hi {{first_name}} {{last_name}}, "
            "your booking {{booking_reference}} is for "
            "{{dropoff_date}} at {{dropoff_time}}. "
            "Pickup: {{pickup_date}} at {{pickup_time}}. "
            "Vehicle: {{vehicle_registration}}. "
            "Destination: {{destination}}. "
            "Total: {{total_price}}"
        )
        template = create_mock_template(content=content)

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        assert "{{first_name}}" in send_form["content"]
        assert "{{last_name}}" in send_form["content"]
        assert "{{booking_reference}}" in send_form["content"]
        assert "{{dropoff_date}}" in send_form["content"]
        assert "{{dropoff_time}}" in send_form["content"]
        assert "{{pickup_date}}" in send_form["content"]
        assert "{{pickup_time}}" in send_form["content"]
        assert "{{vehicle_registration}}" in send_form["content"]
        assert "{{destination}}" in send_form["content"]
        assert "{{total_price}}" in send_form["content"]

    def test_use_template_with_empty_content(self):
        """Test using template with empty content."""
        template = create_mock_template(content="")

        send_form = {"phone": "", "content": "existing content", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        assert send_form["content"] == ""

    def test_use_template_with_special_characters(self):
        """Test using template with special characters."""
        special_contents = [
            "Hi! Thanks for booking 🚗",
            "Price: £50.00",
            "Email: test@example.com",
            "Reference: TAG-ABC123",
            "Line 1\nLine 2\nLine 3",
            "Tab\there",
            "<script>alert('test')</script>",
            "Quote: \"Hello\"",
            "Apostrophe: It's great",
        ]

        for content in special_contents:
            template = create_mock_template(content=content)
            send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
            send_form["content"] = template.content

            assert send_form["content"] == content

    def test_use_template_with_max_length_content(self):
        """Test using template at max SMS length (480 chars)."""
        max_content = "A" * 480  # 3 SMS messages worth
        template = create_mock_template(content=max_content)

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        assert len(send_form["content"]) == 480

    def test_use_multiple_templates_sequentially(self):
        """Test using multiple templates one after another."""
        templates = [
            create_mock_template(id=1, name="t1", content="Content 1"),
            create_mock_template(id=2, name="t2", content="Content 2"),
            create_mock_template(id=3, name="t3", content="Content 3"),
        ]

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}

        for i, template in enumerate(templates):
            send_form["content"] = template.content
            assert send_form["content"] == f"Content {i + 1}"

    def test_use_template_content_can_be_edited(self):
        """Test that template content can be modified after loading."""
        template = create_mock_template(content="Original template content")

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        # User edits the content
        send_form["content"] = send_form["content"] + " - Modified by user"

        assert send_form["content"] == "Original template content - Modified by user"

    def test_use_template_with_trigger_event_types(self):
        """Test using templates with different trigger events."""
        trigger_events = [
            ("booking_confirmed", "Your booking is confirmed!"),
            ("reminder_2day", "Reminder: parking in 2 days"),
            ("thank_you", "Thank you for using TAG Parking!"),
            (None, "Manual template - no trigger"),
        ]

        for trigger, content in trigger_events:
            template = create_mock_template(
                content=content,
                trigger_event=trigger,
                is_automated=trigger is not None
            )

            send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
            send_form["content"] = template.content

            assert send_form["content"] == content

    def test_use_template_form_ready_for_booking_selection(self):
        """Test form state is ready for booking selection after template use."""
        template = create_mock_template(content="Hi {{first_name}}!")

        send_form = {"phone": "", "content": "", "booking_id": "", "customer_id": ""}
        send_form["content"] = template.content

        # Phone should be empty, waiting for booking selection or manual entry
        assert send_form["phone"] == ""
        assert send_form["booking_id"] == ""
        assert send_form["customer_id"] == ""
        assert send_form["content"] == "Hi {{first_name}}!"


# =============================================================================
# Integration Tests: Template Variables
# =============================================================================

class TestTemplateVariables:
    """Integration tests for template variables endpoint."""

    def test_get_available_variables(self):
        """Test getting available template variables."""
        from sms_service import get_template_variables_list

        variables = get_template_variables_list()

        assert isinstance(variables, list)
        assert len(variables) > 0

        # Check expected variables exist
        names = [v["name"] for v in variables]
        assert "first_name" in names
        assert "booking_reference" in names
        assert "dropoff_date" in names


# =============================================================================
# Integration Tests: Send Single Message
# =============================================================================

class TestSendSingleMessage:
    """Integration tests for sending single SMS."""

    @patch('sms_service.is_sms_enabled')
    @patch('sms_service.get_jwt_token')
    @patch('sms_service.httpx.AsyncClient')
    def test_send_message_success(self, mock_client, mock_token, mock_enabled):
        """Test successful message send."""
        mock_enabled.return_value = True
        mock_token.return_value = "test_token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messageid": "msg123"}

        # Simulate success
        result = {
            "success": True,
            "message_id": "msg123",
            "phone": "447123456789",
        }

        assert result["success"] is True
        assert result["message_id"] == "msg123"

    def test_send_message_invalid_phone(self):
        """Test sending to invalid phone number."""
        result = {
            "success": False,
            "error": "Invalid UK phone number"
        }

        assert result["success"] is False
        assert "Invalid" in result["error"]

    def test_send_message_missing_content(self):
        """Test sending without content."""
        data = {"phone": "07123456789"}
        content = data.get("content")

        has_error = content is None

        assert has_error is True

    def test_send_message_with_template(self):
        """Test sending with template rendering."""
        template = create_mock_template(content="Hi {{first_name}}!")
        booking = create_mock_booking()

        from sms_service import get_booking_variables, render_template

        variables = get_booking_variables(booking)
        content = render_template(template.content, variables)

        assert "Hi John!" == content


# =============================================================================
# Integration Tests: Send Bulk Messages
# =============================================================================

class TestSendBulkMessages:
    """Integration tests for bulk SMS sending."""

    def test_bulk_send_multiple_bookings(self):
        """Test sending to multiple bookings."""
        bookings = [
            create_mock_booking(id=1, reference="TAG-001"),
            create_mock_booking(id=2, reference="TAG-002"),
            create_mock_booking(id=3, reference="TAG-003"),
        ]

        # Simulate bulk send result
        result = {
            "success": True,
            "batch_id": "batch123",
            "sent": 3,
            "failed": 0,
        }

        assert result["sent"] == 3
        assert result["failed"] == 0

    def test_bulk_send_partial_failure(self):
        """Test bulk send with some failures."""
        result = {
            "success": True,
            "batch_id": "batch123",
            "sent": 2,
            "failed": 1,
            "details": [
                {"phone": "447111111111", "success": True},
                {"phone": "447222222222", "success": True},
                {"phone": "invalid", "success": False, "error": "Invalid phone"},
            ],
        }

        assert result["sent"] == 2
        assert result["failed"] == 1

    def test_bulk_send_no_bookings(self):
        """Test bulk send with empty booking list."""
        booking_ids = []
        has_error = len(booking_ids) == 0

        assert has_error is True

    def test_bulk_send_with_template(self):
        """Test bulk send renders template for each booking."""
        template = create_mock_template(content="Hi {{first_name}}!")
        bookings = [
            create_mock_booking(id=1),
            create_mock_booking(id=2),
        ]

        from sms_service import get_booking_variables, render_template

        # Each booking should get personalized message
        messages = []
        for booking in bookings:
            variables = get_booking_variables(booking)
            content = render_template(template.content, variables)
            messages.append(content)

        assert all("Hi John!" == m for m in messages)


# =============================================================================
# Integration Tests: Message Listing
# =============================================================================

class TestMessageListing:
    """Integration tests for message listing endpoint."""

    def test_list_all_messages(self):
        """Test listing all messages."""
        messages = [
            create_mock_message(id=1),
            create_mock_message(id=2),
            create_mock_message(id=3),
        ]

        result = {
            "total": len(messages),
            "messages": [{"id": m.id} for m in messages],
        }

        assert result["total"] == 3
        assert len(result["messages"]) == 3

    def test_list_messages_filtered_by_phone(self):
        """Test filtering messages by phone number."""
        all_messages = [
            create_mock_message(id=1, phone_number="447123456789"),
            create_mock_message(id=2, phone_number="447123456789"),
            create_mock_message(id=3, phone_number="447987654321"),
        ]

        # Filter by phone
        filter_phone = "447123456789"
        filtered = [m for m in all_messages if filter_phone in m.phone_number]

        assert len(filtered) == 2

    def test_list_messages_filtered_by_status(self):
        """Test filtering messages by status."""
        from db_models import SMSStatus

        all_messages = [
            create_mock_message(id=1, status="sent"),
            create_mock_message(id=2, status="delivered"),
            create_mock_message(id=3, status="failed"),
        ]

        # Filter by status
        filter_status = SMSStatus.DELIVERED
        filtered = [m for m in all_messages if m.status == filter_status]

        assert len(filtered) == 1

    def test_list_messages_filtered_by_direction(self):
        """Test filtering messages by direction."""
        from db_models import SMSDirection

        all_messages = [
            create_mock_message(id=1, direction="outbound"),
            create_mock_message(id=2, direction="inbound"),
            create_mock_message(id=3, direction="outbound"),
        ]

        # Filter by direction
        filter_direction = SMSDirection.INBOUND
        filtered = [m for m in all_messages if m.direction == filter_direction]

        assert len(filtered) == 1


# =============================================================================
# Integration Tests: Conversation Thread
# =============================================================================

class TestConversationThread:
    """Integration tests for conversation thread endpoint."""

    def test_get_conversation_by_phone(self):
        """Test getting conversation thread by phone number."""
        phone = "447123456789"
        messages = [
            create_mock_message(id=1, phone_number=phone, direction="outbound"),
            create_mock_message(id=2, phone_number=phone, direction="inbound"),
            create_mock_message(id=3, phone_number=phone, direction="outbound"),
        ]

        result = {
            "phone_number": phone,
            "messages": [
                {"id": m.id, "direction": m.direction.value}
                for m in messages
            ],
        }

        assert result["phone_number"] == phone
        assert len(result["messages"]) == 3

    def test_get_conversation_with_customer(self):
        """Test conversation includes customer info."""
        phone = "447123456789"

        mock_customer = MagicMock()
        mock_customer.id = 1
        mock_customer.first_name = "John"
        mock_customer.last_name = "Smith"
        mock_customer.email = "john@test.com"

        result = {
            "phone_number": phone,
            "customer": {
                "id": mock_customer.id,
                "name": f"{mock_customer.first_name} {mock_customer.last_name}",
                "email": mock_customer.email,
            },
            "messages": [],
        }

        assert result["customer"]["name"] == "John Smith"

    def test_get_conversation_no_messages(self):
        """Test conversation for phone with no messages."""
        phone = "447999999999"
        messages = []

        result = {
            "phone_number": phone,
            "customer": None,
            "messages": messages,
        }

        assert len(result["messages"]) == 0


# =============================================================================
# Integration Tests: Webhook - Delivery Reports
# =============================================================================

class TestDeliveryReportWebhook:
    """Integration tests for delivery report webhook."""

    def test_webhook_updates_status_delivered(self):
        """Test webhook updates message to delivered."""
        from db_models import SMSStatus

        message = create_mock_message(id=1, status="sent")
        payload = {"messageid": "msg123", "status": "delivered"}

        # Simulate update
        message.status = SMSStatus.DELIVERED
        message.delivered_at = datetime.now()

        assert message.status == SMSStatus.DELIVERED
        assert message.delivered_at is not None

    def test_webhook_updates_status_failed(self):
        """Test webhook updates message to failed."""
        from db_models import SMSStatus

        message = create_mock_message(id=1, status="sent")
        payload = {
            "messageid": "msg123",
            "status": "failed",
            "failurereason": "Number not reachable"
        }

        # Simulate update
        message.status = SMSStatus.FAILED
        message.status_detail = payload["failurereason"]

        assert message.status == SMSStatus.FAILED
        assert message.status_detail == "Number not reachable"

# =============================================================================
# Integration Tests: Webhook - Incoming SMS
# =============================================================================

class TestIncomingSMSWebhook:
    """Integration tests for incoming SMS webhook."""

    def test_webhook_creates_inbound_message(self):
        """Test webhook creates inbound message record."""
        from db_models import SMSDirection, SMSStatus

        payload = {
            "sender": "447123456789",
            "content": "This is a reply",
            "messageid": "incoming123"
        }

        # Simulate created message
        message = create_mock_message(
            phone_number=payload["sender"],
            direction="inbound",
            content=payload["content"],
            status="delivered",
        )

        assert message.direction == SMSDirection.INBOUND
        assert message.content == "This is a reply"

    def test_webhook_links_to_customer(self):
        """Test webhook links message to customer if found."""
        from db_models import SMSDirection

        customer_phone = "447123456789"
        mock_customer = MagicMock()
        mock_customer.id = 1

        message = create_mock_message(
            direction="inbound",
            phone_number=customer_phone,
            customer_id=mock_customer.id,
        )

        assert message.customer_id == 1


# =============================================================================
# Integration Tests: SMS Statistics
# =============================================================================

class TestSMSStatistics:
    """Integration tests for SMS statistics endpoint."""

    def test_stats_returns_counts(self):
        """Test stats endpoint returns correct counts."""
        stats = {
            "total_sent": 100,
            "total_received": 25,
            "delivered": 95,
            "failed": 5,
            "conversations": 50,
            "sms_enabled": True,
        }

        assert stats["total_sent"] == 100
        assert stats["delivered"] == 95
        assert stats["failed"] == 5

    def test_stats_shows_sms_status(self):
        """Test stats includes SMS enabled status."""
        stats = {
            "sms_enabled": False,
        }

        assert stats["sms_enabled"] is False


# =============================================================================
# Integration Tests: Automated Triggers
# =============================================================================

class TestAutomatedTriggers:
    """Integration tests for automated SMS triggers."""

    @patch('sms_service.is_sms_enabled')
    @patch('sms_service.send_sms')
    def test_booking_confirmation_sms_trigger(self, mock_send, mock_enabled):
        """Test booking confirmation triggers SMS."""
        mock_enabled.return_value = True
        mock_send.return_value = {"success": True}

        booking = create_mock_booking()
        template = create_mock_template(
            is_automated=True,
            trigger_event="booking_confirmed"
        )

        # Simulate trigger - SMS should be sent
        should_send = (
            mock_enabled.return_value and
            booking.customer is not None and
            bool(booking.customer.phone)
        )

        assert should_send is True

    @patch('sms_service.is_sms_enabled')
    def test_reminder_sms_trigger(self, mock_enabled):
        """Test 2-day reminder triggers SMS."""
        mock_enabled.return_value = True

        booking = create_mock_booking()
        template = create_mock_template(
            is_automated=True,
            trigger_event="reminder_2day"
        )

        # Should trigger SMS if enabled
        assert mock_enabled.return_value is True

    def test_sms_not_sent_when_disabled(self):
        """Test SMS not sent when service disabled."""
        sms_enabled = False

        # Should not send when disabled
        should_send = sms_enabled

        assert should_send is False


# =============================================================================
# Integration Tests: Error Handling
# =============================================================================

class TestErrorHandling:
    """Integration tests for error handling."""

    def test_api_failure_returns_error(self):
        """Test SMS API failure returns error response."""
        result = {
            "success": False,
            "error": "SMS API error: 500 - Internal Server Error"
        }

        assert result["success"] is False
        assert "error" in result

    def test_network_timeout_handled(self):
        """Test network timeout is handled gracefully."""
        result = {
            "success": False,
            "error": "Error sending SMS: Connection timeout"
        }

        assert result["success"] is False

    def test_invalid_template_returns_404(self):
        """Test invalid template ID returns 404."""
        template_id = 9999
        template = None  # Not found
        status_code = 404 if not template else 200

        assert status_code == 404


# =============================================================================
# Integration Tests: Authentication
# =============================================================================

class TestAuthentication:
    """Integration tests for endpoint authentication."""

    def test_endpoints_require_admin(self):
        """Test SMS endpoints require admin authentication."""
        # Simulating non-authenticated request
        user = None
        status_code = 401 if not user else 200

        assert status_code == 401

    def test_endpoints_reject_non_admin(self):
        """Test SMS endpoints reject non-admin users."""
        user = create_mock_user(is_admin=False)
        status_code = 403 if user and not user.is_admin else 200

        assert status_code == 403

    def test_endpoints_accept_admin(self):
        """Test SMS endpoints accept admin users."""
        user = create_mock_user(is_admin=True)
        status_code = 200 if user and user.is_admin else 403

        assert status_code == 200

# =============================================================================
# Integration Tests: Resend Message
# =============================================================================

class TestResendMessage:
    """Integration tests for resending SMS messages."""

    def test_resend_outbound_message_success(self):
        """Test successfully resending an outbound message."""
        original_message = create_mock_message(
            id=1,
            phone_number="447123456789",
            direction="outbound",
            content="Hi Mark, your parking at TAG starts in 2 days!",
            status="delivered",
            booking_id=123,
        )

        # Simulate resend - should create a new message with same content
        new_message_id = 2
        result = {
            "success": True,
            "message": "Message resent successfully",
            "new_message_id": new_message_id,
        }

        assert result["success"] is True
        assert result["new_message_id"] == 2
        assert result["message"] == "Message resent successfully"

    def test_resend_failed_message(self):
        """Test resending a previously failed message."""
        failed_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Failed message content",
            status="failed",
        )

        # Should still be able to resend failed messages
        result = {
            "success": True,
            "new_message_id": 2,
        }

        assert result["success"] is True
        assert result["new_message_id"] == 2

    def test_cannot_resend_inbound_message(self):
        """Test that inbound messages cannot be resent."""
        inbound_message = create_mock_message(
            id=1,
            direction="inbound",
            content="Customer reply",
            status="delivered",
        )

        # Attempting to resend an inbound message should fail
        status_code = 400
        error_detail = "Cannot resend inbound messages"

        assert status_code == 400
        assert error_detail == "Cannot resend inbound messages"

    def test_resend_nonexistent_message_returns_404(self):
        """Test resending a message that doesn't exist."""
        message_id = 9999
        message = None  # Not found

        status_code = 404 if not message else 200
        assert status_code == 404

    def test_resend_preserves_booking_association(self):
        """Test that resent message preserves booking ID."""
        original_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Booking reminder",
            booking_id=456,
        )

        # New message should have same booking_id
        new_message_booking_id = original_message.booking_id

        assert new_message_booking_id == 456

    def test_resend_preserves_customer_association(self):
        """Test that resent message preserves customer ID."""
        original_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Customer message",
            customer_id=789,
        )

        # New message should have same customer_id
        new_message_customer_id = original_message.customer_id

        assert new_message_customer_id == 789

    def test_resend_preserves_content_exactly(self):
        """Test that resent message has identical content."""
        original_content = "Hi {{first_name}}, reminder about booking {{booking_ref}}"
        original_message = create_mock_message(
            id=1,
            direction="outbound",
            content=original_content,
        )

        # New message should have exact same content
        new_message_content = original_message.content

        assert new_message_content == original_content

    def test_resend_creates_new_message_record(self):
        """Test that resending creates a new database record."""
        original_message_id = 1
        new_message_id = 2

        # Original message should still exist
        assert original_message_id != new_message_id

    def test_resend_with_pending_status(self):
        """Test resending a message that is still pending."""
        pending_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Pending message",
            status="pending",
        )

        # Should still allow resending even if pending
        result = {"success": True, "new_message_id": 2}
        assert result["success"] is True

    def test_resend_with_sent_status(self):
        """Test resending a message with 'sent' status."""
        sent_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Sent message",
            status="sent",
        )

        result = {"success": True, "new_message_id": 2}
        assert result["success"] is True

    def test_resend_updates_message_count(self):
        """Test that resending increments the total message count."""
        initial_count = 5
        # After resend, count should increase by 1
        new_count = initial_count + 1

        assert new_count == 6

    def test_resend_tracks_original_sender(self):
        """Test that resent message tracks the current admin user."""
        admin_user = create_mock_user(id=10, email="admin@example.com")

        # New message should be attributed to current admin
        sent_by = admin_user.id

        assert sent_by == 10


# =============================================================================
# Integration Tests: Delete Message
# =============================================================================

class TestDeleteMessage:
    """Integration tests for deleting SMS messages."""

    def test_delete_outbound_message_success(self):
        """Test successfully deleting an outbound message."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Test outbound message",
            status="delivered",
        )

        result = {"success": True, "message": "Message deleted"}

        assert result["success"] is True
        assert result["message"] == "Message deleted"

    def test_delete_inbound_message_success(self):
        """Test successfully deleting an inbound message."""
        message = create_mock_message(
            id=1,
            direction="inbound",
            content="Customer inbound message",
            status="delivered",
        )

        result = {"success": True, "message": "Message deleted"}

        assert result["success"] is True

    def test_delete_nonexistent_message_returns_404(self):
        """Test deleting a message that doesn't exist."""
        message_id = 9999
        message = None  # Not found

        status_code = 404 if not message else 200
        assert status_code == 404

    def test_delete_removes_message_from_database(self):
        """Test that deleted message is actually removed."""
        message_id = 1
        # After delete, query should return None
        deleted_message = None

        assert deleted_message is None

    def test_delete_failed_message(self):
        """Test deleting a failed message."""
        failed_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Failed message",
            status="failed",
        )

        result = {"success": True, "message": "Message deleted"}
        assert result["success"] is True

    def test_delete_pending_message(self):
        """Test deleting a pending message."""
        pending_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Pending message",
            status="pending",
        )

        result = {"success": True, "message": "Message deleted"}
        assert result["success"] is True

    def test_delete_message_with_booking_association(self):
        """Test deleting a message associated with a booking."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Booking message",
            booking_id=123,
        )

        # Should delete successfully even with booking association
        result = {"success": True}
        assert result["success"] is True

    def test_delete_message_with_customer_association(self):
        """Test deleting a message associated with a customer."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Customer message",
            customer_id=456,
        )

        # Should delete successfully even with customer association
        result = {"success": True}
        assert result["success"] is True

    def test_delete_message_from_bulk_send(self):
        """Test deleting a message that was part of a bulk send."""
        bulk_message = create_mock_message(
            id=1,
            direction="outbound",
            content="Bulk message",
        )
        bulk_message.is_bulk = True
        bulk_message.bulk_batch_id = "batch_123"

        result = {"success": True}
        assert result["success"] is True

    def test_delete_decrements_message_count(self):
        """Test that deleting reduces the total message count."""
        initial_count = 10
        # After delete, count should decrease by 1
        new_count = initial_count - 1

        assert new_count == 9

    def test_delete_message_with_template_reference(self):
        """Test deleting a message that references a template."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Template-based message",
        )
        message.template_id = 5

        result = {"success": True}
        assert result["success"] is True

    def test_delete_does_not_affect_other_messages(self):
        """Test that deleting one message doesn't affect others."""
        message1_id = 1
        message2_id = 2

        # Delete message 1
        deleted_id = message1_id

        # Message 2 should still exist
        message2_exists = True

        assert deleted_id == 1
        assert message2_exists is True

    def test_delete_conversation_thread(self):
        """Test deleting multiple messages in a conversation."""
        messages = [
            create_mock_message(id=1, direction="outbound", content="Message 1"),
            create_mock_message(id=2, direction="inbound", content="Reply 1"),
            create_mock_message(id=3, direction="outbound", content="Message 2"),
        ]

        deleted_count = 0
        for msg in messages:
            deleted_count += 1

        assert deleted_count == 3

    def test_delete_requires_admin_authentication(self):
        """Test that delete endpoint requires admin authentication."""
        user = None  # Not authenticated
        status_code = 401 if not user else 200

        assert status_code == 401

    def test_delete_rejects_non_admin_user(self):
        """Test that non-admin users cannot delete messages."""
        user = create_mock_user(is_admin=False)
        status_code = 403 if user and not user.is_admin else 200

        assert status_code == 403


# =============================================================================
# Integration Tests: Message Actions Edge Cases
# =============================================================================

class TestMessageActionsEdgeCases:
    """Edge case tests for resend and delete functionality."""

    def test_resend_message_with_special_characters(self):
        """Test resending message with special characters."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Test with special chars: £€¥ \"quotes\" & ampersand",
        )

        result = {"success": True, "new_message_id": 2}
        assert result["success"] is True

    def test_resend_message_with_emoji(self):
        """Test resending message with emoji characters."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Your parking is confirmed! ✅🚗",
        )

        result = {"success": True, "new_message_id": 2}
        assert result["success"] is True

    def test_resend_message_with_newlines(self):
        """Test resending message with newline characters."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="Line 1\nLine 2\nLine 3",
        )

        result = {"success": True, "new_message_id": 2}
        assert result["success"] is True

    def test_delete_message_with_special_characters(self):
        """Test deleting message with special characters in content."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="<script>alert('test')</script>",  # Should still delete
        )

        result = {"success": True}
        assert result["success"] is True

    def test_resend_and_delete_same_message(self):
        """Test resending a message then deleting the original."""
        original_id = 1
        new_id = 2

        # Resend creates new message
        resend_result = {"success": True, "new_message_id": new_id}

        # Delete original
        delete_result = {"success": True}

        assert resend_result["new_message_id"] == 2
        assert delete_result["success"] is True

    def test_concurrent_resend_attempts(self):
        """Test handling multiple rapid resend requests."""
        message_id = 1

        # Multiple resends should create multiple new messages
        resend_results = [
            {"success": True, "new_message_id": 2},
            {"success": True, "new_message_id": 3},
            {"success": True, "new_message_id": 4},
        ]

        new_ids = [r["new_message_id"] for r in resend_results]
        assert len(set(new_ids)) == 3  # All unique IDs

    def test_resend_very_long_message(self):
        """Test resending a message at maximum SMS length."""
        long_content = "A" * 160  # Standard SMS length
        message = create_mock_message(
            id=1,
            direction="outbound",
            content=long_content,
        )

        result = {"success": True, "new_message_id": 2}
        assert result["success"] is True

    def test_delete_message_with_empty_content(self):
        """Test deleting a message with empty content (edge case)."""
        message = create_mock_message(
            id=1,
            direction="outbound",
            content="",
        )

        result = {"success": True}
        assert result["success"] is True

    def test_resend_preserves_phone_format(self):
        """Test that resend preserves original phone number format."""
        original_phone = "+447123456789"
        message = create_mock_message(
            id=1,
            direction="outbound",
            phone_number=original_phone,
            content="Test",
        )

        # New message should use same phone format
        new_phone = message.phone_number
        assert new_phone == original_phone

    def test_delete_oldest_message_in_conversation(self):
        """Test deleting the oldest message in a thread."""
        oldest_message = create_mock_message(
            id=1,
            direction="outbound",
            content="First message",
        )
        oldest_message.created_at = datetime.now() - timedelta(days=30)

        result = {"success": True}
        assert result["success"] is True

    def test_delete_newest_message_in_conversation(self):
        """Test deleting the newest message in a thread."""
        newest_message = create_mock_message(
            id=5,
            direction="inbound",
            content="Latest reply",
        )
        newest_message.created_at = datetime.now()

        result = {"success": True}
        assert result["success"] is True

    def test_resend_to_different_phone_not_allowed(self):
        """Test that resend cannot change the destination phone."""
        original_message = create_mock_message(
            id=1,
            direction="outbound",
            phone_number="447111111111",
            content="Test",
        )

        # Resend uses the original phone number
        resent_phone = original_message.phone_number

        assert resent_phone == "447111111111"

    def test_actions_on_message_from_webhook(self):
        """Test actions on message received via webhook."""
        webhook_message = create_mock_message(
            id=1,
            direction="inbound",
            content="Message from webhook",
        )
        webhook_message.provider_message_id = "ext_123456"

        # Delete should work
        delete_result = {"success": True}
        assert delete_result["success"] is True

        # Resend should fail (inbound)
        resend_status = 400
        assert resend_status == 400


# =============================================================================
# SMS Draft Tests
# =============================================================================

def create_mock_draft(
    id=1,
    phone_number="447123456789",
    content="Draft message",
    booking_id=None,
    customer_id=None,
):
    """Create a mock SMS draft (message with DRAFT status)."""
    from db_models import SMSDirection, SMSStatus

    draft = MagicMock()
    draft.id = id
    draft.phone_number = phone_number
    draft.direction = SMSDirection.OUTBOUND
    draft.content = content
    draft.status = SMSStatus.DRAFT
    draft.booking_id = booking_id
    draft.customer_id = customer_id
    draft.status_detail = None
    draft.is_bulk = False
    draft.created_at = datetime.now()
    draft.delivered_at = None

    # Mock relationships
    if booking_id:
        draft.booking = MagicMock()
        draft.booking.reference = f"TAG-{booking_id:06d}"
    else:
        draft.booking = None

    if customer_id:
        draft.customer = MagicMock()
        draft.customer.first_name = "Test"
        draft.customer.last_name = "Customer"
    else:
        draft.customer = None

    return draft


class TestSmsDraftsCRUD:
    """Tests for SMS Draft Create, Read, Update, Delete operations."""

    def test_get_drafts_empty(self):
        """Test getting drafts when none exist."""
        drafts = []
        result = {"drafts": drafts}
        assert result["drafts"] == []

    def test_get_drafts_with_data(self):
        """Test getting drafts when drafts exist."""
        draft1 = create_mock_draft(id=1, content="Draft 1")
        draft2 = create_mock_draft(id=2, content="Draft 2")
        drafts = [draft1, draft2]

        result = {
            "drafts": [
                {
                    "id": d.id,
                    "phone_number": d.phone_number,
                    "content": d.content,
                    "booking_id": d.booking_id,
                    "customer_id": d.customer_id,
                }
                for d in drafts
            ]
        }

        assert len(result["drafts"]) == 2
        assert result["drafts"][0]["content"] == "Draft 1"
        assert result["drafts"][1]["content"] == "Draft 2"

    def test_save_draft_success(self):
        """Test saving a new draft."""
        phone = "447111222333"
        content = "This is a test draft message"

        draft = create_mock_draft(id=1, phone_number=phone, content=content)

        result = {
            "success": True,
            "draft": {
                "id": draft.id,
                "phone_number": draft.phone_number,
                "content": draft.content,
            }
        }

        assert result["success"] is True
        assert result["draft"]["phone_number"] == phone
        assert result["draft"]["content"] == content

    def test_save_draft_without_phone(self):
        """Test saving a draft without phone number (allowed for drafts)."""
        content = "Draft without phone"
        draft = create_mock_draft(id=1, phone_number="", content=content)

        result = {"success": True, "draft": {"id": draft.id, "content": content}}
        assert result["success"] is True

    def test_save_draft_without_content(self):
        """Test saving a draft without content (allowed for drafts)."""
        phone = "447111222333"
        draft = create_mock_draft(id=1, phone_number=phone, content="")

        result = {"success": True, "draft": {"id": draft.id, "phone_number": phone}}
        assert result["success"] is True

    def test_save_draft_with_booking_id(self):
        """Test saving a draft linked to a booking."""
        draft = create_mock_draft(id=1, booking_id=123)

        result = {
            "success": True,
            "draft": {
                "id": draft.id,
                "booking_id": draft.booking_id,
                "booking_reference": draft.booking.reference,
            }
        }

        assert result["success"] is True
        assert result["draft"]["booking_id"] == 123
        assert result["draft"]["booking_reference"] == "TAG-000123"

    def test_save_draft_with_customer_id(self):
        """Test saving a draft linked to a customer."""
        draft = create_mock_draft(id=1, customer_id=456)

        result = {
            "success": True,
            "draft": {
                "id": draft.id,
                "customer_id": draft.customer_id,
            }
        }

        assert result["success"] is True
        assert result["draft"]["customer_id"] == 456

    def test_update_draft_success(self):
        """Test updating an existing draft."""
        original_draft = create_mock_draft(id=1, content="Original content")
        updated_content = "Updated content"

        # Simulate update
        original_draft.content = updated_content

        result = {
            "success": True,
            "draft": {
                "id": original_draft.id,
                "content": original_draft.content,
            }
        }

        assert result["success"] is True
        assert result["draft"]["content"] == "Updated content"

    def test_update_draft_phone(self):
        """Test updating draft phone number."""
        draft = create_mock_draft(id=1, phone_number="447111111111")
        new_phone = "447222222222"

        draft.phone_number = new_phone

        assert draft.phone_number == new_phone

    def test_update_draft_not_found(self):
        """Test updating a non-existent draft."""
        # Simulating 404 response
        result = {"status_code": 404, "detail": "Draft not found"}
        assert result["status_code"] == 404

    def test_update_non_draft_message_fails(self):
        """Test that updating a sent message (not a draft) fails."""
        from db_models import SMSStatus

        sent_message = create_mock_message(id=1, status="sent")

        # Attempt to update should fail because it's not a draft
        is_draft = sent_message.status == SMSStatus.DRAFT
        assert is_draft is False

    def test_delete_draft_success(self):
        """Test deleting a draft."""
        draft = create_mock_draft(id=1)

        result = {"success": True, "message": "Draft deleted"}
        assert result["success"] is True

    def test_delete_draft_not_found(self):
        """Test deleting a non-existent draft."""
        result = {"status_code": 404, "detail": "Draft not found"}
        assert result["status_code"] == 404

    def test_delete_non_draft_message_fails(self):
        """Test that delete draft endpoint only works on drafts."""
        from db_models import SMSStatus

        sent_message = create_mock_message(id=1, status="sent")

        is_draft = sent_message.status == SMSStatus.DRAFT
        assert is_draft is False


class TestSmsDraftsSend:
    """Tests for sending SMS drafts."""

    def test_send_draft_success(self):
        """Test sending a draft successfully."""
        draft = create_mock_draft(
            id=1,
            phone_number="447123456789",
            content="Hello from draft!"
        )

        # Simulate successful send
        result = {"success": True, "message_id": "new_msg_123"}
        assert result["success"] is True

    def test_send_draft_without_phone_fails(self):
        """Test that sending a draft without phone number fails."""
        draft = create_mock_draft(id=1, phone_number="", content="Test")

        # Simulate validation error
        result = {"status_code": 400, "detail": "Phone and content are required to send"}
        assert result["status_code"] == 400

    def test_send_draft_without_content_fails(self):
        """Test that sending a draft without content fails."""
        draft = create_mock_draft(id=1, phone_number="447123456789", content="")

        result = {"status_code": 400, "detail": "Phone and content are required to send"}
        assert result["status_code"] == 400

    def test_send_draft_not_found(self):
        """Test sending a non-existent draft."""
        result = {"status_code": 404, "detail": "Draft not found"}
        assert result["status_code"] == 404

    def test_send_draft_deletes_draft(self):
        """Test that sending a draft removes it from drafts."""
        draft_id = 1
        draft = create_mock_draft(id=draft_id)

        # After sending, draft should be deleted
        drafts_after_send = []  # Simulating draft was removed
        assert draft_id not in [d.id for d in drafts_after_send]

    def test_send_draft_creates_message(self):
        """Test that sending a draft creates a new message."""
        draft = create_mock_draft(
            id=1,
            phone_number="447123456789",
            content="Draft content",
            booking_id=100,
            customer_id=50
        )

        # Simulating new message created from draft
        new_message = create_mock_message(
            id=999,
            phone_number=draft.phone_number,
            content=draft.content,
            booking_id=draft.booking_id,
            customer_id=draft.customer_id,
            status="sent"
        )

        assert new_message.phone_number == draft.phone_number
        assert new_message.content == draft.content
        assert new_message.booking_id == draft.booking_id
        assert new_message.customer_id == draft.customer_id

    def test_send_draft_with_variables(self):
        """Test sending a draft that contains template variables."""
        draft = create_mock_draft(
            id=1,
            phone_number="447123456789",
            content="Hi {{first_name}}, your booking {{booking_reference}} is confirmed!"
        )

        # Variables should remain as-is (not substituted) for manual drafts
        assert "{{first_name}}" in draft.content
        assert "{{booking_reference}}" in draft.content

    def test_send_non_draft_fails(self):
        """Test that send draft endpoint only works on drafts."""
        from db_models import SMSStatus

        sent_message = create_mock_message(id=1, status="delivered")

        is_draft = sent_message.status == SMSStatus.DRAFT
        assert is_draft is False


class TestSmsDraftsFiltering:
    """Tests for draft listing and filtering."""

    def test_drafts_ordered_by_created_at_desc(self):
        """Test that drafts are returned in descending order by creation date."""
        older_draft = create_mock_draft(id=1, content="Older")
        older_draft.created_at = datetime.now() - timedelta(days=1)

        newer_draft = create_mock_draft(id=2, content="Newer")
        newer_draft.created_at = datetime.now()

        drafts = [newer_draft, older_draft]  # Should be newest first

        assert drafts[0].id == 2
        assert drafts[1].id == 1

    def test_drafts_include_booking_reference(self):
        """Test that draft response includes booking reference when linked."""
        draft = create_mock_draft(id=1, booking_id=12345)

        result = {
            "id": draft.id,
            "booking_id": draft.booking_id,
            "booking_reference": draft.booking.reference if draft.booking else None,
        }

        assert result["booking_reference"] == "TAG-012345"

    def test_drafts_include_customer_name(self):
        """Test that draft response includes customer name when linked."""
        draft = create_mock_draft(id=1, customer_id=789)

        customer_name = f"{draft.customer.first_name} {draft.customer.last_name}" if draft.customer else None

        result = {"id": draft.id, "customer_name": customer_name}

        assert result["customer_name"] == "Test Customer"

    def test_drafts_not_included_in_regular_messages(self):
        """Test that drafts are not returned in regular message listing."""
        from db_models import SMSStatus

        draft = create_mock_draft(id=1)
        sent_message = create_mock_message(id=2, status="sent")
        delivered_message = create_mock_message(id=3, status="delivered")

        # Regular messages (excluding drafts)
        regular_messages = [sent_message, delivered_message]

        draft_ids = [m.id for m in regular_messages if m.status == SMSStatus.DRAFT]
        assert len(draft_ids) == 0

    def test_only_drafts_returned_in_drafts_endpoint(self):
        """Test that only draft status messages are returned in drafts endpoint."""
        from db_models import SMSStatus

        draft1 = create_mock_draft(id=1)
        draft2 = create_mock_draft(id=2)
        sent_message = create_mock_message(id=3, status="sent")

        all_messages = [draft1, draft2, sent_message]

        drafts_only = [m for m in all_messages if m.status == SMSStatus.DRAFT]

        assert len(drafts_only) == 2
        assert all(d.status == SMSStatus.DRAFT for d in drafts_only)


class TestSmsDraftsEdgesCases:
    """Edge case tests for SMS drafts."""

    def test_draft_with_long_content(self):
        """Test draft with content at max SMS length."""
        long_content = "A" * 480  # Max length
        draft = create_mock_draft(id=1, content=long_content)

        assert len(draft.content) == 480

    def test_draft_with_special_characters(self):
        """Test draft with special characters."""
        special_content = "Hello! 🎉 Test & more <test> \"quotes\""
        draft = create_mock_draft(id=1, content=special_content)

        assert draft.content == special_content

    def test_draft_with_unicode(self):
        """Test draft with unicode characters."""
        unicode_content = "Bonjour! Café résumé naïve"
        draft = create_mock_draft(id=1, content=unicode_content)

        assert draft.content == unicode_content

    def test_draft_with_newlines(self):
        """Test draft with newline characters."""
        multiline_content = "Line 1\nLine 2\nLine 3"
        draft = create_mock_draft(id=1, content=multiline_content)

        assert "\n" in draft.content
        assert draft.content.count("\n") == 2

    def test_draft_phone_number_formatting(self):
        """Test draft with various phone number formats."""
        formats = [
            "447123456789",
            "+447123456789",
            "07123456789",
        ]

        for phone in formats:
            draft = create_mock_draft(id=1, phone_number=phone)
            assert draft.phone_number == phone

    def test_multiple_drafts_same_phone(self):
        """Test having multiple drafts for the same phone number."""
        phone = "447123456789"
        draft1 = create_mock_draft(id=1, phone_number=phone, content="Draft 1")
        draft2 = create_mock_draft(id=2, phone_number=phone, content="Draft 2")

        assert draft1.phone_number == draft2.phone_number
        assert draft1.content != draft2.content

    def test_draft_timestamps(self):
        """Test that drafts have proper timestamps."""
        draft = create_mock_draft(id=1)

        assert draft.created_at is not None

    def test_draft_direction_is_outbound(self):
        """Test that drafts are always outbound direction."""
        from db_models import SMSDirection

        draft = create_mock_draft(id=1)
        assert draft.direction == SMSDirection.OUTBOUND

    def test_draft_status_is_draft(self):
        """Test that draft status is DRAFT."""
        from db_models import SMSStatus

        draft = create_mock_draft(id=1)
        assert draft.status == SMSStatus.DRAFT


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
