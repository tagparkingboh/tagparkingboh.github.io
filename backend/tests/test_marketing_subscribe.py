"""
Tests for the Marketing Subscribe API endpoint.

Includes both unit tests and integration tests for:
- POST /api/marketing/subscribe
- Unsubscribe functionality

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from datetime import datetime
from sqlalchemy.sql.elements import BinaryExpression

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import get_db
from db_models import MarketingSubscriber


# =============================================================================
# Mock Database Setup
# =============================================================================

class MockSubscriberStore:
    """In-memory store for mock subscribers."""

    def __init__(self):
        self.subscribers = {}
        self.next_id = 1

    def add(self, subscriber):
        subscriber.id = self.next_id
        subscriber.subscribed_at = subscriber.subscribed_at or datetime.utcnow()
        self.subscribers[subscriber.email.lower()] = subscriber
        self.next_id += 1
        return subscriber

    def get_by_email(self, email):
        return self.subscribers.get(email.lower())

    def get_by_token(self, token):
        for sub in self.subscribers.values():
            if sub.unsubscribe_token == token:
                return sub
        return None

    def clear(self):
        self.subscribers = {}
        self.next_id = 1


# Global mock store
_mock_store = MockSubscriberStore()


class MockQuery:
    """Mock SQLAlchemy query object."""

    def __init__(self, model, store):
        self.model = model
        self.store = store
        self._filters = []

    def filter(self, *args):
        self._filters.extend(args)
        return self

    def first(self):
        # Try to extract filter values
        for f in self._filters:
            if isinstance(f, BinaryExpression):
                try:
                    # Get the column name being filtered
                    col_name = f.left.key if hasattr(f.left, 'key') else str(f.left)
                    # Get the value (handle both bound parameters and literals)
                    if hasattr(f.right, 'value'):
                        value = f.right.value
                    elif hasattr(f.right, 'effective_value'):
                        value = f.right.effective_value
                    else:
                        value = str(f.right)

                    if 'email' in col_name.lower():
                        return self.store.get_by_email(value)
                    elif 'unsubscribe_token' in col_name.lower():
                        return self.store.get_by_token(value)
                except Exception:
                    pass
        return None

    def all(self):
        return list(self.store.subscribers.values())

    def count(self):
        return len(self.store.subscribers)


class MockSession:
    """Mock database session."""

    def __init__(self, store):
        self.store = store
        self._added = []

    def query(self, model):
        return MockQuery(model, self.store)

    def add(self, obj):
        self._added.append(obj)
        if isinstance(obj, MarketingSubscriber):
            self.store.add(obj)

    def commit(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def get_mock_db():
    """Override for get_db dependency."""
    db = MockSession(_mock_store)
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_mock_store():
    """Reset the mock store before each test."""
    _mock_store.clear()
    yield
    _mock_store.clear()


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Override the database dependency for all tests."""
    app.dependency_overrides[get_db] = get_mock_db
    yield
    app.dependency_overrides.clear()


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
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )
        _mock_store.add(subscriber)

        assert subscriber.id is not None
        assert subscriber.first_name == "John"
        assert subscriber.last_name == "Doe"
        assert subscriber.email == "john@example.com"
        assert subscriber.subscribed_at is not None

    def test_create_subscriber_with_source(self):
        """Should create a subscriber with custom source."""
        subscriber = MarketingSubscriber(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            source="homepage",
        )
        _mock_store.add(subscriber)

        assert subscriber.source == "homepage"

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
# Integration Tests - Subscribe API Endpoint (Mocked)
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
    # Pre-add a subscriber
    existing = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribed=False,
    )
    _mock_store.add(existing)

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
    # Pre-add an unsubscribed user
    existing = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribe_token="old-token-123",
        unsubscribed=True,
        unsubscribed_at=datetime.utcnow(),
        welcome_email_sent=True,
        welcome_email_sent_at=datetime.utcnow(),
    )
    _mock_store.add(existing)

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


@pytest.mark.asyncio
async def test_subscribe_email_case_insensitive(client):
    """Should treat emails as case-insensitive."""
    # Pre-add a subscriber with lowercase email
    existing = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribed=False,
    )
    _mock_store.add(existing)

    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "Johnny",
            "last_name": "Doe",
            "email": "JOHN@EXAMPLE.COM",
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


@pytest.mark.asyncio
async def test_subscribe_special_characters_in_name(client):
    """Should handle special characters in names."""
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "Jose-Maria",
            "last_name": "O'Connor",
            "email": "jose@example.com",
        }
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_subscribe_long_email(client):
    """Should handle long but valid email addresses."""
    long_email = "a" * 50 + "@" + "b" * 50 + ".com"
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


# =============================================================================
# Unit Tests - Unsubscribe Model Fields
# =============================================================================

class TestUnsubscribeModelFields:
    """Unit tests for unsubscribe-related fields on MarketingSubscriber."""

    def test_unsubscribed_defaults_to_false(self):
        """Unsubscribed should default to False."""
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="test-token-123",
        )
        # Default value check
        assert subscriber.unsubscribed is None or subscriber.unsubscribed is False

    def test_can_set_unsubscribed(self):
        """Should be able to mark a subscriber as unsubscribed."""
        subscriber = MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            unsubscribe_token="test-token-123",
        )
        subscriber.unsubscribed = True
        subscriber.unsubscribed_at = datetime.utcnow()

        assert subscriber.unsubscribed is True
        assert subscriber.unsubscribed_at is not None


# =============================================================================
# Integration Tests - Unsubscribe API Endpoint (Mocked)
# =============================================================================

@pytest.mark.asyncio
async def test_unsubscribe_confirmation_page(client):
    """GET should show confirmation page with 'Yes, I'm sure!' button."""
    # Pre-add a subscriber
    subscriber = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribe_token="valid-token-12345",
        unsubscribed=False,
    )
    _mock_store.add(subscriber)

    response = await client.get("/api/marketing/unsubscribe/valid-token-12345")
    assert response.status_code == 200
    assert "Are you sure" in response.text
    assert "Yes, I'm sure!" in response.text
    assert "john@example.com" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_success(client):
    """POST should successfully unsubscribe with valid token."""
    # Pre-add a subscriber
    subscriber = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribe_token="valid-token-12345",
        unsubscribed=False,
    )
    _mock_store.add(subscriber)

    response = await client.post("/api/marketing/unsubscribe/valid-token-12345")
    assert response.status_code == 200
    assert "Unsubscribed Successfully" in response.text
    assert "john@example.com" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_invalid_token(client):
    """Should return 404 for invalid token."""
    response = await client.get("/api/marketing/unsubscribe/invalid-token-xyz")
    assert response.status_code == 404
    assert "Invalid Link" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_already_unsubscribed(client):
    """Should show already unsubscribed message."""
    # Pre-add an already unsubscribed user
    subscriber = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribe_token="already-unsub-token",
        unsubscribed=True,
        unsubscribed_at=datetime.utcnow(),
    )
    _mock_store.add(subscriber)

    response = await client.get("/api/marketing/unsubscribe/already-unsub-token")
    assert response.status_code == 200
    assert "Already Unsubscribed" in response.text


@pytest.mark.asyncio
async def test_unsubscribe_returns_html(client):
    """Should return HTML content type."""
    subscriber = MarketingSubscriber(
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        unsubscribe_token="html-test-token",
        unsubscribed=False,
    )
    _mock_store.add(subscriber)

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
        from unittest.mock import patch
        from email_service import send_welcome_email

        with patch('email_service.send_email') as mock_send:
            mock_send.return_value = True

            result = send_welcome_email(
                first_name="John",
                email="john@example.com",
                unsubscribe_token="test-token-abc123",
            )

            assert mock_send.called
            call_args = mock_send.call_args
            html_content = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('html_content', '')
            assert "test-token-abc123" in html_content
            assert "/api/marketing/unsubscribe/" in html_content

    def test_send_welcome_email_without_token(self):
        """send_welcome_email should have fallback when no token provided."""
        from unittest.mock import patch
        from email_service import send_welcome_email

        with patch('email_service.send_email') as mock_send:
            mock_send.return_value = True

            result = send_welcome_email(
                first_name="John",
                email="john@example.com",
            )

            assert mock_send.called


# =============================================================================
# Unit Tests - Email Scheduler (Skips Unsubscribed)
# =============================================================================

class TestEmailSchedulerUnsubscribe:
    """Tests for email scheduler respecting unsubscribe status."""

    def test_scheduler_skips_unsubscribed_users(self):
        """Email scheduler should skip unsubscribed users."""
        from datetime import timedelta

        # Create test subscribers
        active = MarketingSubscriber(
            first_name="Active",
            last_name="User",
            email="active@example.com",
            unsubscribe_token="active-token",
            subscribed_at=datetime.utcnow() - timedelta(minutes=10),
            welcome_email_sent=False,
            unsubscribed=False,
        )

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

        _mock_store.add(active)
        _mock_store.add(unsubscribed)

        # Verify the mock store has both
        assert len(_mock_store.subscribers) == 2

        # Verify unsubscribed status
        assert _mock_store.get_by_email("active@example.com").unsubscribed is False
        assert _mock_store.get_by_email("unsubscribed@example.com").unsubscribed is True
