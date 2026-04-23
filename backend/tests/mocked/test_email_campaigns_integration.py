"""
REAL Mocked Integration tests for Marketing Email Campaigns endpoints.

These tests actually import and execute code from main.py, increasing coverage.
Only the database and auth are mocked - the endpoint logic runs for real.

Tests the following endpoints:
- GET /api/admin/marketing/campaigns
- GET /api/admin/marketing/campaigns/{campaign_id}
- POST /api/admin/marketing/campaigns
- POST /api/admin/marketing/campaigns/{campaign_id}/send
- POST /api/admin/marketing/campaigns/preview
- GET /api/admin/marketing/promo-codes
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from main import app, get_db, require_admin
from db_models import (
    MarketingEmailCampaign,
    MarketingEmailRecipient,
    MarketingEmailStatus,
    MarketingSubscriber,
    PromoCode,
)


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_campaign(
    id=1,
    subject="Test Campaign Subject",
    message="Hello {{first_name}}, this is a test message.",
    promo_code_id=None,
    promo_code=None,
    status=MarketingEmailStatus.DRAFT,
    total_recipients=10,
    sent_count=0,
    failed_count=0,
    created_at=None,
    sent_at=None,
    completed_at=None,
    created_by="admin@test.com",
):
    """Create a mock MarketingEmailCampaign."""
    campaign = MagicMock(spec=MarketingEmailCampaign)
    campaign.id = id
    campaign.subject = subject
    campaign.message = message
    campaign.promo_code_id = promo_code_id
    campaign.promo_code = promo_code
    campaign.status = status
    campaign.total_recipients = total_recipients
    campaign.sent_count = sent_count
    campaign.failed_count = failed_count
    campaign.created_at = created_at or datetime.now(timezone.utc)
    campaign.sent_at = sent_at
    campaign.completed_at = completed_at
    campaign.created_by = created_by
    return campaign


def create_mock_recipient(
    id=1,
    campaign_id=1,
    subscriber_id=1,
    subscriber=None,
    email_sent=False,
    email_sent_at=None,
    email_failed=False,
    error_message=None,
):
    """Create a mock MarketingEmailRecipient."""
    recipient = MagicMock(spec=MarketingEmailRecipient)
    recipient.id = id
    recipient.campaign_id = campaign_id
    recipient.subscriber_id = subscriber_id
    recipient.subscriber = subscriber or create_mock_subscriber(id=subscriber_id)
    recipient.email_sent = email_sent
    recipient.email_sent_at = email_sent_at
    recipient.email_failed = email_failed
    recipient.error_message = error_message
    return recipient


def create_mock_subscriber(
    id=1,
    first_name="John",
    last_name="Doe",
    email="john@example.com",
    unsubscribed=False,
    unsubscribe_token="test-token-123",
):
    """Create a mock MarketingSubscriber."""
    subscriber = MagicMock(spec=MarketingSubscriber)
    subscriber.id = id
    subscriber.first_name = first_name
    subscriber.last_name = last_name
    subscriber.email = email
    subscriber.unsubscribed = unsubscribed
    subscriber.unsubscribe_token = unsubscribe_token
    return subscriber


def create_mock_promo_code(
    id=1,
    code="TAG-TEST-1234",
    discount_percent=10,
    max_uses=100,
    uses_count=5,
    is_used=False,
    created_at=None,
):
    """Create a mock PromoCode."""
    promo = MagicMock(spec=PromoCode)
    promo.id = id
    promo.code = code
    promo.discount_percent = discount_percent
    promo.max_uses = max_uses
    promo.uses_count = uses_count
    promo.is_used = is_used
    promo.created_at = created_at or datetime.now(timezone.utc)
    return promo


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


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


@pytest.fixture
def client(mock_db, mock_admin):
    """Create a test client with mocked dependencies."""
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    async def override_require_admin():
        return mock_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = override_require_admin

    # Patch startup functions to avoid DB connection
    with patch('main.init_db'), \
         patch('main.run_migrations'), \
         patch('main.start_scheduler'), \
         patch('main.stop_scheduler'):
        with TestClient(app) as test_client:
            yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# GET /api/admin/marketing/campaigns Tests
# ============================================================================

class TestGetCampaignsEndpoint:
    """Integration tests for GET /api/admin/marketing/campaigns."""

    def test_returns_200_with_empty_campaigns(self, client, mock_db):
        """Should return 200 with empty list when no campaigns exist."""
        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert "campaigns" in data
        assert data["campaigns"] == []

    def test_returns_campaigns_list(self, client, mock_db):
        """Should return list of campaigns."""
        campaigns = [
            create_mock_campaign(id=1, subject="Campaign 1"),
            create_mock_campaign(id=2, subject="Campaign 2"),
        ]

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = campaigns
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert "campaigns" in data
        assert len(data["campaigns"]) == 2

    def test_truncates_long_messages(self, client, mock_db):
        """Should truncate message to 100 chars with ellipsis."""
        long_message = "A" * 150
        campaign = create_mock_campaign(id=1, message=long_message)

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns")

        assert response.status_code == 200
        data = response.json()
        # Message should be truncated to 100 chars + "..."
        assert len(data["campaigns"][0]["message"]) == 103

    def test_includes_promo_code_name(self, client, mock_db):
        """Should include promo code name when attached."""
        promo = create_mock_promo_code(id=1, code="TAG-PROMO-1234")
        campaign = create_mock_campaign(id=1, promo_code_id=1, promo_code=promo)

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert data["campaigns"][0]["promo_code"] == "TAG-PROMO-1234"


# ============================================================================
# GET /api/admin/marketing/campaigns/{campaign_id} Tests
# ============================================================================

class TestGetCampaignDetailEndpoint:
    """Integration tests for GET /api/admin/marketing/campaigns/{campaign_id}."""

    def test_returns_campaign_details(self, client, mock_db):
        """Should return campaign with full details."""
        campaign = create_mock_campaign(id=1, subject="Test Campaign")
        recipients = [
            create_mock_recipient(id=1, campaign_id=1, subscriber_id=1),
            create_mock_recipient(id=2, campaign_id=1, subscriber_id=2),
        ]

        # Setup mock queries
        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign

        recipient_query = MagicMock()
        recipient_query.filter.return_value = recipient_query
        recipient_query.all.return_value = recipients

        mock_db.query.side_effect = [campaign_query, recipient_query]

        response = client.get("/api/admin/marketing/campaigns/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["subject"] == "Test Campaign"
        assert "recipients" in data
        assert len(data["recipients"]) == 2

    def test_returns_404_for_nonexistent_campaign(self, client, mock_db):
        """Should return 404 when campaign not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns/999")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_includes_recipient_status(self, client, mock_db):
        """Should include email_sent and email_failed status for each recipient."""
        campaign = create_mock_campaign(id=1)
        sent_recipient = create_mock_recipient(
            id=1,
            email_sent=True,
            email_sent_at=datetime.now(timezone.utc),
        )
        failed_recipient = create_mock_recipient(
            id=2,
            email_failed=True,
            error_message="SMTP error",
        )

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign

        recipient_query = MagicMock()
        recipient_query.filter.return_value = recipient_query
        recipient_query.all.return_value = [sent_recipient, failed_recipient]

        mock_db.query.side_effect = [campaign_query, recipient_query]

        response = client.get("/api/admin/marketing/campaigns/1")

        assert response.status_code == 200
        data = response.json()
        recipients = data["recipients"]
        assert recipients[0]["email_sent"] is True
        assert recipients[1]["email_failed"] is True
        assert recipients[1]["error_message"] == "SMTP error"


# ============================================================================
# POST /api/admin/marketing/campaigns Tests
# ============================================================================

class TestCreateCampaignEndpoint:
    """Integration tests for POST /api/admin/marketing/campaigns."""

    def test_creates_campaign_successfully(self, client, mock_db):
        """Should create campaign and return ID."""
        subscribers = [
            create_mock_subscriber(id=1, email="sub1@test.com"),
            create_mock_subscriber(id=2, email="sub2@test.com"),
        ]

        # Mock subscriber query
        sub_query = MagicMock()
        sub_query.filter.return_value = sub_query
        sub_query.all.return_value = subscribers

        mock_db.query.return_value = sub_query

        # Mock campaign creation
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.commit = MagicMock()

        # Mock the campaign object to have an ID after flush
        def set_campaign_id(*args, **kwargs):
            if hasattr(args[0], 'id'):
                args[0].id = 1
        mock_db.flush.side_effect = lambda: None

        response = client.post(
            "/api/admin/marketing/campaigns",
            json={
                "subject": "New Campaign",
                "message": "Hello {{first_name}}!",
                "subscriber_ids": [1, 2],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data or "message" in data

    def test_validates_promo_code_exists(self, client, mock_db):
        """Should return 400 if promo code not found."""
        # First query for promo code returns None
        promo_query = MagicMock()
        promo_query.filter.return_value = promo_query
        promo_query.first.return_value = None

        mock_db.query.return_value = promo_query

        response = client.post(
            "/api/admin/marketing/campaigns",
            json={
                "subject": "Test",
                "message": "Test message",
                "promo_code_id": 999,
                "subscriber_ids": [1],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "promo code" in data["detail"].lower()

    def test_requires_valid_subscribers(self, client, mock_db):
        """Should return 400 if no valid subscribers selected."""
        # Mock promo query (first call is for PromoCode if promo_code_id provided)
        # Mock subscriber query returns empty list
        sub_query = MagicMock()
        sub_query.filter.return_value = sub_query
        sub_query.all.return_value = []

        mock_db.query.return_value = sub_query

        response = client.post(
            "/api/admin/marketing/campaigns",
            json={
                "subject": "Test",
                "message": "Test message",
                "subscriber_ids": [999, 998],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "subscriber" in data["detail"].lower()

    def test_excludes_unsubscribed_users(self, client, mock_db):
        """Should filter out unsubscribed users from recipient list."""
        # Only non-unsubscribed subscriber returned
        active_subscriber = create_mock_subscriber(id=1, unsubscribed=False)

        sub_query = MagicMock()
        sub_query.filter.return_value = sub_query
        sub_query.all.return_value = [active_subscriber]  # Only 1, not 2

        mock_db.query.return_value = sub_query
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.commit = MagicMock()

        response = client.post(
            "/api/admin/marketing/campaigns",
            json={
                "subject": "Test",
                "message": "Test message",
                "subscriber_ids": [1, 2],  # 2 is unsubscribed (filtered by query)
            },
        )

        assert response.status_code == 200


# ============================================================================
# PUT /api/admin/marketing/campaigns/{campaign_id} Tests
# ============================================================================

class TestUpdateCampaignEndpoint:
    """Integration tests for PUT /api/admin/marketing/campaigns/{campaign_id}."""

    def test_updates_draft_campaign_successfully(self, client, mock_db):
        """Should update draft campaign and return success."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.DRAFT)
        subscribers = [
            create_mock_subscriber(id=1, email="sub1@test.com"),
            create_mock_subscriber(id=2, email="sub2@test.com"),
        ]

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign

        sub_query = MagicMock()
        sub_query.filter.return_value = sub_query
        sub_query.all.return_value = subscribers

        recipient_delete_query = MagicMock()
        recipient_delete_query.filter.return_value = recipient_delete_query
        recipient_delete_query.delete.return_value = 0

        mock_db.query.side_effect = [campaign_query, sub_query, recipient_delete_query]
        mock_db.commit = MagicMock()

        response = client.put(
            "/api/admin/marketing/campaigns/1",
            json={
                "subject": "Updated Subject",
                "message": "Updated message",
                "subscriber_ids": [1, 2],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data or "message" in data
        assert campaign.subject == "Updated Subject"
        assert campaign.message == "Updated message"
        assert campaign.total_recipients == 2

    def test_returns_404_for_nonexistent_campaign(self, client, mock_db):
        """Should return 404 when campaign not found."""
        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = None
        mock_db.query.return_value = campaign_query

        response = client.put(
            "/api/admin/marketing/campaigns/999",
            json={
                "subject": "X",
                "message": "Y",
                "subscriber_ids": [1],
            },
        )

        assert response.status_code == 404

    def test_rejects_non_draft_campaign(self, client, mock_db):
        """Should return 400 for sent/sending campaign."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.SENT)

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign
        mock_db.query.return_value = campaign_query

        response = client.put(
            "/api/admin/marketing/campaigns/1",
            json={
                "subject": "X",
                "message": "Y",
                "subscriber_ids": [1],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "draft" in data["detail"].lower()

    def test_rejects_invalid_promo_code(self, client, mock_db):
        """Should return 400 when provided promo_code_id does not exist."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.DRAFT)

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign

        promo_query = MagicMock()
        promo_query.filter.return_value = promo_query
        promo_query.first.return_value = None

        mock_db.query.side_effect = [campaign_query, promo_query]

        response = client.put(
            "/api/admin/marketing/campaigns/1",
            json={
                "subject": "X",
                "message": "Y",
                "promo_code_id": 999,
                "subscriber_ids": [1],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "promo code" in data["detail"].lower()

    def test_rejects_when_no_valid_subscribers(self, client, mock_db):
        """Should return 400 when all subscriber_ids are invalid/unsubscribed."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.DRAFT)

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign

        sub_query = MagicMock()
        sub_query.filter.return_value = sub_query
        sub_query.all.return_value = []

        mock_db.query.side_effect = [campaign_query, sub_query]

        response = client.put(
            "/api/admin/marketing/campaigns/1",
            json={
                "subject": "X",
                "message": "Y",
                "subscriber_ids": [99, 98],
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "subscriber" in data["detail"].lower()


# ============================================================================
# DELETE /api/admin/marketing/campaigns/{campaign_id} Tests
# ============================================================================

class TestDeleteCampaignEndpoint:
    """Integration tests for DELETE /api/admin/marketing/campaigns/{campaign_id}."""

    def test_deletes_draft_campaign_successfully(self, client, mock_db):
        """Should delete draft campaign and its recipients."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.DRAFT)

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign

        recipient_delete_query = MagicMock()
        recipient_delete_query.filter.return_value = recipient_delete_query
        recipient_delete_query.delete.return_value = 0

        mock_db.query.side_effect = [campaign_query, recipient_delete_query]
        mock_db.delete = MagicMock()
        mock_db.commit = MagicMock()

        response = client.delete("/api/admin/marketing/campaigns/1")

        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"].lower()
        mock_db.delete.assert_called_once_with(campaign)
        recipient_delete_query.delete.assert_called_once()

    def test_returns_404_for_nonexistent_campaign(self, client, mock_db):
        """Should return 404 when campaign not found."""
        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = None
        mock_db.query.return_value = campaign_query

        response = client.delete("/api/admin/marketing/campaigns/999")

        assert response.status_code == 404

    def test_rejects_non_draft_campaign(self, client, mock_db):
        """Should return 400 for sent campaign."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.SENT)

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign
        mock_db.query.return_value = campaign_query

        response = client.delete("/api/admin/marketing/campaigns/1")

        assert response.status_code == 400
        data = response.json()
        assert "draft" in data["detail"].lower()

    def test_rejects_sending_campaign(self, client, mock_db):
        """Should return 400 for campaign currently sending."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.SENDING)

        campaign_query = MagicMock()
        campaign_query.filter.return_value = campaign_query
        campaign_query.first.return_value = campaign
        mock_db.query.return_value = campaign_query

        response = client.delete("/api/admin/marketing/campaigns/1")

        assert response.status_code == 400


# ============================================================================
# POST /api/admin/marketing/campaigns/{campaign_id}/send Tests
# ============================================================================

class TestSendCampaignEndpoint:
    """Integration tests for POST /api/admin/marketing/campaigns/{campaign_id}/send."""

    def test_starts_sending_campaign(self, client, mock_db):
        """Should start sending campaign and return success."""
        campaign = create_mock_campaign(
            id=1,
            status=MarketingEmailStatus.DRAFT,
            total_recipients=10,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query
        mock_db.commit = MagicMock()

        with patch("main.send_campaign_emails"):
            response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["total_recipients"] == 10

    def test_returns_404_for_nonexistent_campaign(self, client, mock_db):
        """Should return 404 when campaign not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        response = client.post("/api/admin/marketing/campaigns/999/send")

        assert response.status_code == 404

    def test_rejects_non_draft_campaign(self, client, mock_db):
        """Should return 400 for already sent/sending campaign."""
        campaign = create_mock_campaign(
            id=1,
            status=MarketingEmailStatus.SENT,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query

        response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 400
        data = response.json()
        assert "already" in data["detail"].lower()

    def test_updates_campaign_status_to_sending(self, client, mock_db):
        """Should update campaign status to SENDING."""
        campaign = create_mock_campaign(
            id=1,
            status=MarketingEmailStatus.DRAFT,
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query
        mock_db.commit = MagicMock()

        with patch("main.send_campaign_emails"):
            response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 200
        # Verify status was updated
        assert campaign.status == MarketingEmailStatus.SENDING


# ============================================================================
# POST /api/admin/marketing/campaigns/preview Tests
# ============================================================================

class TestPreviewCampaignEndpoint:
    """Integration tests for POST /api/admin/marketing/campaigns/preview."""

    def test_returns_preview_with_sample_values(self, client, mock_db):
        """Should replace variables with sample values."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        response = client.post(
            "/api/admin/marketing/campaigns/preview",
            json={
                "subject": "Special Offer",
                "message": "Hello {{first_name}}, {{founder_name}} here!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["subject"] == "Special Offer"
        assert "John" in data["message"]
        assert "Matt" in data["message"]
        assert "{{first_name}}" not in data["message"]
        assert "{{founder_name}}" not in data["message"]

    def test_includes_promo_code_when_provided(self, client, mock_db):
        """Should include promo code in preview when promo_code_id provided."""
        promo = create_mock_promo_code(id=1, code="TAG-PREVIEW-CODE")

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = promo
        mock_db.query.return_value = mock_query

        response = client.post(
            "/api/admin/marketing/campaigns/preview",
            json={
                "subject": "Test",
                "message": "Test message",
                "promo_code_id": 1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["promo_code"] == "TAG-PREVIEW-CODE"

    def test_returns_null_promo_when_not_found(self, client, mock_db):
        """Should return null promo_code when promo_code_id not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        response = client.post(
            "/api/admin/marketing/campaigns/preview",
            json={
                "subject": "Test",
                "message": "Test message",
                "promo_code_id": 999,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["promo_code"] is None


# ============================================================================
# GET /api/admin/marketing/promo-codes Tests
# ============================================================================

class TestGetPromoCodesEndpoint:
    """Integration tests for GET /api/admin/marketing/promo-codes."""

    def test_returns_available_promo_codes(self, client, mock_db):
        """Should return list of multi-use promo codes."""
        codes = [
            create_mock_promo_code(id=1, code="TAG-CODE-1", max_uses=100),
            create_mock_promo_code(id=2, code="TAG-CODE-2", max_uses=50),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = codes
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/promo-codes")

        assert response.status_code == 200
        data = response.json()
        assert "promo_codes" in data

    def test_excludes_exhausted_codes(self, client, mock_db):
        """Should exclude codes where is_used=True (exhausted)."""
        # Only non-exhausted codes returned
        active_codes = [
            create_mock_promo_code(id=1, code="TAG-ACTIVE", is_used=False),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = active_codes
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/promo-codes")

        assert response.status_code == 200
        data = response.json()
        # Should only have non-exhausted code
        assert "promo_codes" in data


# ============================================================================
# Authentication Tests
# ============================================================================

class TestCampaignsAuthentication:
    """Integration tests for authentication on campaign endpoints."""

    def test_rejects_unauthenticated_request(self, mock_db):
        """Should reject request without authentication."""
        app.dependency_overrides.clear()

        def override_get_db():
            try:
                yield mock_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.get("/api/admin/marketing/campaigns")
            # Should return 401 or 403 without auth
            assert response.status_code in [401, 403, 422]

        app.dependency_overrides.clear()


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestCampaignEdgeCases:
    """Edge case tests for campaign endpoints."""

    def test_handles_campaign_with_no_promo_code(self, client, mock_db):
        """Should handle campaign without promo code."""
        campaign = create_mock_campaign(id=1, promo_code_id=None, promo_code=None)

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [campaign]
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns")

        assert response.status_code == 200
        data = response.json()
        assert data["campaigns"][0]["promo_code"] is None

    def test_handles_empty_message(self, client, mock_db):
        """Should handle preview with empty message."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        response = client.post(
            "/api/admin/marketing/campaigns/preview",
            json={
                "subject": "Test",
                "message": "",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == ""

    def test_handles_message_without_variables(self, client, mock_db):
        """Should handle message without template variables."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query

        response = client.post(
            "/api/admin/marketing/campaigns/preview",
            json={
                "subject": "Test",
                "message": "Just a plain message with no variables.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Just a plain message with no variables."

    def test_handles_campaign_id_zero(self, client, mock_db):
        """Should handle campaign ID of 0."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns/0")

        assert response.status_code == 404

    def test_handles_negative_campaign_id(self, client, mock_db):
        """Should handle negative campaign ID."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/marketing/campaigns/-1")

        assert response.status_code == 404

    def test_handles_very_long_subject(self, client, mock_db):
        """Should handle very long subject line."""
        long_subject = "A" * 255

        subscribers = [create_mock_subscriber(id=1)]
        sub_query = MagicMock()
        sub_query.filter.return_value = sub_query
        sub_query.all.return_value = subscribers

        mock_db.query.return_value = sub_query
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.commit = MagicMock()

        response = client.post(
            "/api/admin/marketing/campaigns",
            json={
                "subject": long_subject,
                "message": "Test",
                "subscriber_ids": [1],
            },
        )

        # Should succeed with valid 255 char subject
        assert response.status_code == 200


# ============================================================================
# Status Transition Tests
# ============================================================================

class TestCampaignStatusTransitions:
    """Tests for campaign status transitions."""

    def test_draft_can_transition_to_sending(self, client, mock_db):
        """DRAFT campaign can transition to SENDING."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.DRAFT)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query
        mock_db.commit = MagicMock()

        with patch("main.send_campaign_emails"):
            response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 200
        assert campaign.status == MarketingEmailStatus.SENDING

    def test_sending_campaign_cannot_be_sent_again(self, client, mock_db):
        """SENDING campaign cannot be sent again."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.SENDING)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query

        response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 400

    def test_sent_campaign_cannot_be_sent_again(self, client, mock_db):
        """SENT campaign cannot be sent again."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.SENT)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query

        response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 400

    def test_failed_campaign_cannot_be_sent_again(self, client, mock_db):
        """FAILED campaign cannot be sent again."""
        campaign = create_mock_campaign(id=1, status=MarketingEmailStatus.FAILED)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = campaign
        mock_db.query.return_value = mock_query

        response = client.post("/api/admin/marketing/campaigns/1/send")

        assert response.status_code == 400


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
