"""
Tests for the Marketing Subscribe API endpoint.

Includes both unit tests and integration tests for:
- POST /api/marketing/subscribe
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from database import Base, get_db
from db_models import MarketingSubscriber


# =============================================================================
# Test Database Setup
# =============================================================================

# Use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_marketing.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override the database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
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
        db = TestingSessionLocal()
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
        db = TestingSessionLocal()
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
        db = TestingSessionLocal()
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
    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
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

    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
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

    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
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

    db = TestingSessionLocal()
    try:
        count = db.query(MarketingSubscriber).count()
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

    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
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

    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
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

    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
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

    db = TestingSessionLocal()
    try:
        subscriber = db.query(MarketingSubscriber).first()
        assert subscriber.email == "john+tag@example.com"
    finally:
        db.close()
