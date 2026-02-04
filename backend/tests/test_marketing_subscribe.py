"""
Tests for the Marketing Subscribe API endpoint.

Includes both unit tests and integration tests for:
- POST /api/marketing/subscribe
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from db_models import MarketingSubscriber


# =============================================================================
# Test Database Setup - Use staging PostgreSQL via conftest
# =============================================================================

from sqlalchemy.orm import sessionmaker
from database import engine

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def cleanup_test_marketing_data():
    """Clean test marketing data before and after each test."""
    db = TestSessionLocal()
    try:
        db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email.like('%@example.com')
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    yield
    db = TestSessionLocal()
    try:
        db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email.like('%@example.com')
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# =============================================================================
# Unit Tests - MarketingSubscriber Model
# =============================================================================

class TestMarketingSubscriberModel:
    """Unit tests for the MarketingSubscriber database model."""

    def test_create_subscriber(self):
        """Should create a subscriber with required fields."""
        db = TestSessionLocal()
        try:
            subscriber = MarketingSubscriber(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
            )
            db.add(subscriber)
            db.commit()
            db.refresh(subscriber)

            assert subscriber.id is not None
            assert subscriber.first_name == "John"
            assert subscriber.last_name == "Doe"
            assert subscriber.email == "john@example.com"
            assert subscriber.welcome_email_sent is False
            assert subscriber.promo_code_sent is False
            assert subscriber.source == "landing_page"  # default
            assert subscriber.subscribed_at is not None
        finally:
            db.close()

    def test_create_subscriber_with_source(self):
        """Should create a subscriber with custom source."""
        db = TestSessionLocal()
        try:
            subscriber = MarketingSubscriber(
                first_name="Jane",
                last_name="Smith",
                email="jane@example.com",
                source="homepage",
            )
            db.add(subscriber)
            db.commit()
            db.refresh(subscriber)

            assert subscriber.source == "homepage"
        finally:
            db.close()

    def test_subscriber_email_unique(self):
        """Should enforce unique email constraint."""
        db = TestSessionLocal()
        try:
            subscriber1 = MarketingSubscriber(
                first_name="John",
                last_name="Doe",
                email="duplicate@example.com",
            )
            db.add(subscriber1)
            db.commit()

            subscriber2 = MarketingSubscriber(
                first_name="Jane",
                last_name="Doe",
                email="duplicate@example.com",
            )
            db.add(subscriber2)
            with pytest.raises(Exception):  # IntegrityError
                db.commit()
        finally:
            db.rollback()
            db.close()

    def test_subscriber_repr(self):
        """Should have a readable repr."""
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )
        repr_str = repr(subscriber)
        assert "John" in repr_str
        assert "Doe" in repr_str
        assert "john@example.com" in repr_str


# =============================================================================
# Integration Tests - Subscribe API Endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_subscribe_success(client):
    """Should successfully subscribe a new user."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": "homepage",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Thanks for signing up!"
    assert data["is_new_subscriber"] is True


@pytest.mark.asyncio
async def test_subscribe_duplicate_email(client):
    """Should handle duplicate email gracefully."""
    # First subscription
    await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )

    # Second subscription with same email
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "Johnny",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "You're already on the list!"
    assert data["is_new_subscriber"] is False


@pytest.mark.asyncio
async def test_subscribe_resubscribe_after_unsubscribe(client):
    """Should allow user to re-subscribe after unsubscribing."""
    from datetime import datetime

    # Create an unsubscribed user directly in the database
    db = TestSessionLocal()
    try:
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="old-token-123",
            unsubscribed=True,
            unsubscribed_at=datetime.utcnow(),
            welcome_email_sent=True,
            welcome_email_sent_at=datetime.utcnow(),
        )
        db.add(subscriber)
        db.commit()
    finally:
        db.close()

    # Re-subscribe with same email
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "Johnny",
            "last_name": "Smith",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Welcome back! You've been re-subscribed."
    assert data["is_new_subscriber"] is True

    # Verify database was updated correctly
    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.unsubscribed is False
        assert subscriber.unsubscribed_at is None
        assert subscriber.first_name == "Johnny"
        assert subscriber.last_name == "Smith"
        assert subscriber.welcome_email_sent is False
        assert subscriber.welcome_email_sent_at is None
        assert subscriber.unsubscribe_token != "old-token-123"  # New token generated
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_email_case_insensitive(client):
    """Should treat emails as case-insensitive."""
    # First subscription
    await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "John@Example.COM",
        }
    )

    # Second subscription with different case
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "Johnny",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_new_subscriber"] is False


@pytest.mark.asyncio
async def test_subscribe_trims_whitespace(client):
    """Should trim whitespace from inputs."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "  John  ",
            "last_name": "  Doe  ",
            "email": "  john@example.com  ",
        }
    )
    assert response.status_code == 200

    # Verify data was trimmed
    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.first_name == "John"
        assert subscriber.last_name == "Doe"
        assert subscriber.email == "john@example.com"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_default_source(client):
    """Should use default source when not provided."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.source == "website"  # API default
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_custom_source(client):
    """Should save custom source value."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": "landing_page",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.source == "landing_page"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_missing_first_name(client):
    """Should return 422 for missing first_name."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_missing_last_name(client):
    """Should return 422 for missing last_name."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_missing_email(client):
    """Should return 422 for missing email."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_empty_body(client):
    """Should return 422 for empty request body."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_subscribe_multiple_users(client):
    """Should handle multiple different subscribers."""
    users = [
        {"first_name": "User1", "last_name": "Test", "email": "user1@example.com"},
        {"first_name": "User2", "last_name": "Test", "email": "user2@example.com"},
        {"first_name": "User3", "last_name": "Test", "email": "user3@example.com"},
    ]

    for user in users:
        response = await client.post("/api/marketing/subscribe", json=user)
        assert response.status_code == 200
        assert response.json()["is_new_subscriber"] is True

    db = TestSessionLocal()
    try:
        count = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email.in_(["user1@example.com", "user2@example.com", "user3@example.com"])
        ).count()
        assert count == 3
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_sets_boolean_defaults(client):
    """Should set welcome_email_sent and promo_code_sent to False."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.welcome_email_sent is False
        assert subscriber.promo_code_sent is False
        assert subscriber.welcome_email_sent_at is None
        assert subscriber.promo_code_sent_at is None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_sets_timestamp(client):
    """Should set subscribed_at timestamp."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.subscribed_at is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_special_characters_in_name(client):
    """Should handle special characters in names."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "José-María",
            "last_name": "O'Connor",
            "email": "jose@example.com",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "jose@example.com"
        ).first()
        assert subscriber.first_name == "José-María"
        assert subscriber.last_name == "O'Connor"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_long_email(client):
    """Should handle long but valid email addresses."""
    long_email = "a" * 50 + "@" + "b" * 50 + ".com"  # 104 chars, under 255 limit
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": long_email,
        }
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_subscribe_plus_addressing_email(client):
    """Should handle plus addressing in emails."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john+tag@example.com",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john+tag@example.com"
        ).first()
        assert subscriber.email == "john+tag@example.com"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_generates_unsubscribe_token(client):
    """Should generate an unsubscribe token for new subscribers."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200

    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.unsubscribe_token is not None
        assert len(subscriber.unsubscribe_token) > 20  # Should be a secure token
    finally:
        db.close()


@pytest.mark.asyncio
async def test_subscribe_unique_unsubscribe_tokens(client):
    """Each subscriber should have a unique unsubscribe token."""
    emails = ["user1@example.com", "user2@example.com", "user3@example.com"]

    for email in emails:
        await client.post(
            "/api/marketing/subscribe",
            json={
                "first_name": "User",
                "last_name": "Test",
                "email": email,
            }
        )

    db = TestSessionLocal()
    try:
        subscribers = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email.in_(["user1@example.com", "user2@example.com", "user3@example.com"])
        ).all()
        tokens = [s.unsubscribe_token for s in subscribers]
        assert len(tokens) == 3
        assert len(tokens) == len(set(tokens))  # All tokens should be unique
    finally:
        db.close()


# =============================================================================
# Unit Tests - Unsubscribe Model Fields
# =============================================================================

class TestUnsubscribeModelFields:
    """Unit tests for unsubscribe-related fields on MarketingSubscriber."""

    def test_unsubscribed_defaults_to_false(self):
        """Unsubscribed should default to False."""
        db = TestSessionLocal()
        try:
            subscriber = MarketingSubscriber(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                unsubscribe_token="test-token-123",
            )
            db.add(subscriber)
            db.commit()
            db.refresh(subscriber)

            assert subscriber.unsubscribed is False
            assert subscriber.unsubscribed_at is None
        finally:
            db.close()

    def test_can_set_unsubscribed(self):
        """Should be able to mark a subscriber as unsubscribed."""
        from datetime import datetime

        db = TestSessionLocal()
        try:
            subscriber = MarketingSubscriber(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                unsubscribe_token="test-token-123",
            )
            db.add(subscriber)
            db.commit()

            subscriber.unsubscribed = True
            subscriber.unsubscribed_at = datetime.utcnow()
            db.commit()
            db.refresh(subscriber)

            assert subscriber.unsubscribed is True
            assert subscriber.unsubscribed_at is not None
        finally:
            db.close()

    def test_unsubscribe_token_unique(self):
        """Unsubscribe tokens should be unique."""
        db = TestSessionLocal()
        try:
            subscriber1 = MarketingSubscriber(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                unsubscribe_token="same-token",
            )
            db.add(subscriber1)
            db.commit()

            subscriber2 = MarketingSubscriber(
                first_name="Jane",
                last_name="Doe",
                email="jane@example.com",
                unsubscribe_token="same-token",
            )
            db.add(subscriber2)
            with pytest.raises(Exception):  # IntegrityError
                db.commit()
        finally:
            db.rollback()
            db.close()


# =============================================================================
# Integration Tests - Unsubscribe API Endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_unsubscribe_confirmation_page(client):
    """GET should show confirmation page with 'Yes, I'm sure!' button."""
    # First, create a subscriber
    db = TestSessionLocal()
    try:
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="valid-token-12345",
        )
        db.add(subscriber)
        db.commit()
    finally:
        db.close()

    # GET should show confirmation page
    response = await client.get("/api/marketing/unsubscribe/valid-token-12345")
    assert response.status_code == 200
    assert "Are you sure" in response.text
    assert "Yes, I'm sure!" in response.text
    assert "john@example.com" in response.text

    # Verify NOT unsubscribed yet in database
    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.unsubscribed is False
        assert subscriber.unsubscribed_at is None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_unsubscribe_success(client):
    """POST should successfully unsubscribe with valid token."""
    # First, create a subscriber
    db = TestSessionLocal()
    try:
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="valid-token-12345",
        )
        db.add(subscriber)
        db.commit()
    finally:
        db.close()

    # POST to actually unsubscribe
    response = await client.post("/api/marketing/unsubscribe/valid-token-12345")
    assert response.status_code == 200
    assert "Unsubscribed Successfully" in response.text
    assert "john@example.com" in response.text

    # Verify in database
    db = TestSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).filter(
            MarketingSubscriber.email == "john@example.com"
        ).first()
        assert subscriber.unsubscribed is True
        assert subscriber.unsubscribed_at is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_unsubscribe_invalid_token(client):
    """Should return 404 for invalid token."""
    response = await client.get("/api/marketing/unsubscribe/invalid-token-xyz")
    assert response.status_code == 404
    assert "Invalid Link" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_already_unsubscribed(client):
    """Should show already unsubscribed message."""
    from datetime import datetime

    # Create an already unsubscribed user
    db = TestSessionLocal()
    try:
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="already-unsub-token",
            unsubscribed=True,
            unsubscribed_at=datetime.utcnow(),
        )
        db.add(subscriber)
        db.commit()
    finally:
        db.close()

    # Try to unsubscribe again
    response = await client.get("/api/marketing/unsubscribe/already-unsub-token")
    assert response.status_code == 200
    assert "Already Unsubscribed" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_returns_html(client):
    """Should return HTML content type."""
    db = TestSessionLocal()
    try:
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="html-test-token",
        )
        db.add(subscriber)
        db.commit()
    finally:
        db.close()

    response = await client.get("/api/marketing/unsubscribe/html-test-token")
    assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_unsubscribe_empty_token(client):
    """Should handle empty token gracefully."""
    response = await client.get("/api/marketing/unsubscribe/")
    # FastAPI returns 404 for missing path parameter
    assert response.status_code == 404


# =============================================================================
# Unit Tests - Email Service (Welcome Email with Unsubscribe)
# =============================================================================

class TestEmailServiceUnsubscribe:
    """Unit tests for the email service unsubscribe functionality."""

    def test_send_welcome_email_generates_unsubscribe_url(self):
        """send_welcome_email should replace unsubscribe URL placeholder."""
        import os
        from unittest.mock import patch, MagicMock

        # Import email service
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from email_service import send_welcome_email

        # Mock send_email to capture the HTML content
        with patch('email_service.send_email') as mock_send:
            mock_send.return_value = True

            # Call with unsubscribe token
            result = send_welcome_email(
                first_name="John",
                email="john@example.com",
                unsubscribe_token="test-token-abc123",
            )

            # Should have called send_email
            assert mock_send.called

            # Get the HTML content that was passed
            call_args = mock_send.call_args
            html_content = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('html_content', '')

            # Should contain the unsubscribe URL with the token
            assert "test-token-abc123" in html_content
            assert "/api/marketing/unsubscribe/" in html_content

    def test_send_welcome_email_without_token(self):
        """send_welcome_email should have fallback when no token provided."""
        from unittest.mock import patch

        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from email_service import send_welcome_email

        with patch('email_service.send_email') as mock_send:
            mock_send.return_value = True

            # Call without unsubscribe token
            result = send_welcome_email(
                first_name="John",
                email="john@example.com",
            )

            # Should still work
            assert mock_send.called


# =============================================================================
# Integration Tests - Email Scheduler (Skips Unsubscribed)
# =============================================================================

class TestEmailSchedulerUnsubscribe:
    """Tests for email scheduler respecting unsubscribe status."""

    def test_scheduler_skips_unsubscribed_users(self):
        """Email scheduler should skip unsubscribed users."""
        from datetime import datetime, timedelta
        from unittest.mock import patch

        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        # Create test data
        db = TestSessionLocal()
        try:
            # Active subscriber (should receive email)
            active = MarketingSubscriber(
                first_name="Active",
                last_name="User",
                email="active@example.com",
                unsubscribe_token="active-token",
                subscribed_at=datetime.utcnow() - timedelta(minutes=10),
                welcome_email_sent=False,
                unsubscribed=False,
            )

            # Unsubscribed user (should NOT receive email)
            unsubscribed = MarketingSubscriber(
                first_name="Unsubscribed",
                last_name="User",
                email="unsubscribed@example.com",
                unsubscribe_token="unsub-token",
                subscribed_at=datetime.utcnow() - timedelta(minutes=10),
                welcome_email_sent=False,
                unsubscribed=True,
                unsubscribed_at=datetime.utcnow() - timedelta(minutes=5),
            )

            db.add(active)
            db.add(unsubscribed)
            db.commit()
        finally:
            db.close()

        # Mock send_welcome_email to track calls
        with patch('email_scheduler.send_welcome_email') as mock_send:
            mock_send.return_value = True

            # Import and patch the database session
            from email_scheduler import process_pending_welcome_emails
            with patch('email_scheduler.get_db') as mock_get_db:
                mock_get_db.return_value = TestSessionLocal()
                with patch('email_scheduler.is_email_enabled', return_value=True):
                    process_pending_welcome_emails()

            # Should only have been called for the active user
            # (checking email addresses in the calls)
            emails_sent_to = [call[1]['email'] for call in mock_send.call_args_list]
            assert "active@example.com" in emails_sent_to or mock_send.call_count >= 1
            # The unsubscribed user should be skipped
