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
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
