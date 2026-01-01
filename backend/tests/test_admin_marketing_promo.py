"""
Tests for Admin Marketing Promo Code functionality.

Includes unit tests and integration tests for:
- GET /api/admin/marketing-subscribers
- POST /api/admin/marketing-subscribers/{id}/send-promo

Uses staging database with proper cleanup.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from db_models import MarketingSubscriber


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_subscribers(db_session):
    """Create sample subscribers for testing with unique emails."""
    import secrets
    unique_suffix = secrets.token_hex(4)

    subscribers = [
        MarketingSubscriber(
            first_name="John",
            last_name="Doe",
            email=f"john-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"token-john-{unique_suffix}",
            subscribed_at=datetime.utcnow() - timedelta(days=5),
            welcome_email_sent=True,
            welcome_email_sent_at=datetime.utcnow() - timedelta(days=4),
        ),
        MarketingSubscriber(
            first_name="Jane",
            last_name="Smith",
            email=f"jane-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"token-jane-{unique_suffix}",
            subscribed_at=datetime.utcnow() - timedelta(days=3),
            welcome_email_sent=True,
            welcome_email_sent_at=datetime.utcnow() - timedelta(days=2),
        ),
        MarketingSubscriber(
            first_name="Bob",
            last_name="Wilson",
            email=f"bob-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"token-bob-{unique_suffix}",
            subscribed_at=datetime.utcnow() - timedelta(days=1),
            welcome_email_sent=False,
        ),
    ]
    for sub in subscribers:
        db_session.add(sub)
    db_session.commit()

    # Refresh to get IDs
    for sub in subscribers:
        db_session.refresh(sub)

    ids = [sub.id for sub in subscribers]
    yield ids

    # Cleanup: Remove test subscribers
    for sub_id in ids:
        sub = db_session.query(MarketingSubscriber).filter(
            MarketingSubscriber.id == sub_id
        ).first()
        if sub:
            db_session.delete(sub)
    db_session.commit()


# =============================================================================
# Unit Tests - MarketingSubscriber Promo Fields
# =============================================================================

class TestMarketingSubscriberPromoFields:
    """Unit tests for promo-related fields on MarketingSubscriber."""

    def test_promo_fields_default_values(self, db_session):
        """Promo fields should have correct defaults."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-defaults-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
        )
        db_session.add(subscriber)
        db_session.commit()
        db_session.refresh(subscriber)

        try:
            assert subscriber.promo_code is None
            assert subscriber.promo_code_sent is False
            assert subscriber.promo_code_sent_at is None
            # discount_percent defaults to 10 in the model
            assert subscriber.discount_percent == 10
            assert subscriber.promo_code_used is False
            assert subscriber.promo_code_used_at is None
            assert subscriber.promo_code_used_booking_id is None
        finally:
            db_session.delete(subscriber)
            db_session.commit()

    def test_can_set_promo_code(self, db_session):
        """Should be able to set a promo code."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-setcode-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
        )
        db_session.add(subscriber)
        db_session.commit()

        try:
            subscriber.promo_code = f"TAG-TEST-{unique_suffix[:8].upper()}"
            subscriber.discount_percent = 10
            subscriber.promo_code_sent = True
            subscriber.promo_code_sent_at = datetime.utcnow()
            db_session.commit()
            db_session.refresh(subscriber)

            assert subscriber.promo_code.startswith("TAG-TEST-")
            assert subscriber.discount_percent == 10
            assert subscriber.promo_code_sent is True
            assert subscriber.promo_code_sent_at is not None
        finally:
            db_session.delete(subscriber)
            db_session.commit()

    def test_can_set_100_percent_discount(self, db_session):
        """Should support 100% discount for free parking."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-100off-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
            promo_code=f"TAG-FREE-{unique_suffix[:8].upper()}",
            discount_percent=100,
            promo_code_sent=True,
        )
        db_session.add(subscriber)
        db_session.commit()
        db_session.refresh(subscriber)

        try:
            assert subscriber.discount_percent == 100
        finally:
            db_session.delete(subscriber)
            db_session.commit()

    def test_can_mark_promo_used(self, db_session):
        """Should be able to mark promo as used."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-used-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
            promo_code=f"TAG-USED-{unique_suffix[:8].upper()}",
            discount_percent=10,
            promo_code_sent=True,
        )
        db_session.add(subscriber)
        db_session.commit()

        try:
            subscriber.promo_code_used = True
            subscriber.promo_code_used_at = datetime.utcnow()
            # Don't set booking_id as it would require a real booking
            db_session.commit()
            db_session.refresh(subscriber)

            assert subscriber.promo_code_used is True
            assert subscriber.promo_code_used_at is not None
        finally:
            db_session.delete(subscriber)
            db_session.commit()


# =============================================================================
# Integration Tests - GET /api/admin/marketing-subscribers
# =============================================================================

@pytest.mark.asyncio
async def test_get_subscribers_success(client, sample_subscribers):
    """Should return list of subscribers (no auth required for admin endpoints)."""
    response = await client.get("/api/admin/marketing-subscribers")

    assert response.status_code == 200
    data = response.json()

    assert "count" in data
    assert "subscribers" in data
    # Should contain at least our test subscribers
    assert data["count"] >= 3


@pytest.mark.asyncio
async def test_get_subscribers_returns_all_fields(client, sample_subscribers):
    """Should return all required fields for each subscriber."""
    response = await client.get("/api/admin/marketing-subscribers")

    data = response.json()

    # Find one of our test subscribers
    test_sub = next(
        (s for s in data["subscribers"] if "test-promo.example.com" in s["email"]),
        None
    )
    assert test_sub is not None

    required_fields = [
        "id", "first_name", "last_name", "email", "subscribed_at",
        "welcome_email_sent", "welcome_email_sent_at",
        "promo_code", "promo_code_sent", "promo_code_sent_at",
        "discount_percent", "promo_code_used", "promo_code_used_at",
        "unsubscribed", "unsubscribed_at"
    ]
    for field in required_fields:
        assert field in test_sub, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_get_subscribers_ordered_by_date_desc(client, sample_subscribers):
    """Should return subscribers ordered by subscribed_at descending."""
    response = await client.get("/api/admin/marketing-subscribers")

    data = response.json()

    # Filter to just our test subscribers
    test_subs = [s for s in data["subscribers"] if "test-promo.example.com" in s["email"]]

    # Most recent should be Bob (subscribed 1 day ago)
    # Oldest should be John (subscribed 5 days ago)
    if len(test_subs) >= 3:
        # Bob should appear before Jane who should appear before John
        bob_idx = next((i for i, s in enumerate(test_subs) if s["first_name"] == "Bob"), -1)
        jane_idx = next((i for i, s in enumerate(test_subs) if s["first_name"] == "Jane"), -1)
        john_idx = next((i for i, s in enumerate(test_subs) if s["first_name"] == "John"), -1)

        assert bob_idx < jane_idx < john_idx, "Subscribers should be ordered by subscribed_at desc"


# =============================================================================
# Integration Tests - POST /api/admin/marketing-subscribers/{id}/send-promo
# =============================================================================

@pytest.mark.asyncio
async def test_send_promo_10_percent_success(client, sample_subscribers):
    """Should successfully send 10% promo code."""
    subscriber_id = sample_subscribers[0]

    with patch('email_service.send_promo_code_email') as mock_email:
        mock_email.return_value = True

        response = await client.post(
            f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=10"
        )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "promo_code" in data
    assert data["promo_code"].startswith("TAG-")
    assert data["discount_percent"] == 10
    assert "message" in data  # Email is in the message


@pytest.mark.asyncio
async def test_send_promo_100_percent_success(client, sample_subscribers):
    """Should successfully send 100% (free) promo code."""
    subscriber_id = sample_subscribers[1]  # Use Jane

    # send_free_parking_promo_email is defined in main.py, not email_service
    with patch('main.send_free_parking_promo_email') as mock_email:
        mock_email.return_value = True

        response = await client.post(
            f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=100"
        )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["discount_percent"] == 100


@pytest.mark.asyncio
async def test_send_promo_generates_unique_code(client, sample_subscribers):
    """Should generate unique promo codes for each subscriber."""
    codes = []

    with patch('email_service.send_promo_code_email') as mock_email:
        mock_email.return_value = True

        for subscriber_id in sample_subscribers:
            response = await client.post(
                f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=10"
            )
            if response.status_code == 200:
                codes.append(response.json()["promo_code"])

    # All codes should be unique
    assert len(codes) == len(set(codes))


@pytest.mark.asyncio
async def test_send_promo_updates_database(client, db_session, sample_subscribers):
    """Should update subscriber record in database."""
    subscriber_id = sample_subscribers[0]

    with patch('email_service.send_promo_code_email') as mock_email:
        mock_email.return_value = True

        response = await client.post(
            f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=10"
        )

    assert response.status_code == 200

    # Verify database was updated - need fresh session
    db_session.expire_all()
    subscriber = db_session.query(MarketingSubscriber).filter(
        MarketingSubscriber.id == subscriber_id
    ).first()

    assert subscriber.promo_code is not None
    assert subscriber.promo_code_sent is True
    assert subscriber.promo_code_sent_at is not None
    assert subscriber.discount_percent == 10


@pytest.mark.asyncio
async def test_send_promo_subscriber_not_found(client):
    """Should return 404 for non-existent subscriber."""
    response = await client.post(
        "/api/admin/marketing-subscribers/999999/send-promo?discount_percent=10"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_promo_invalid_discount_percent(client, sample_subscribers):
    """Should return 400 for invalid discount percentage."""
    subscriber_id = sample_subscribers[0]

    response = await client.post(
        f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=50"
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_send_promo_to_unsubscribed_user(client, db_session):
    """Should return 400 when sending to unsubscribed user."""
    import secrets
    unique_suffix = secrets.token_hex(4)

    subscriber = MarketingSubscriber(
        first_name="Unsubscribed",
        last_name="User",
        email=f"unsub-{unique_suffix}@test-promo.example.com",
        unsubscribe_token=f"unsub-token-{unique_suffix}",
        unsubscribed=True,
        unsubscribed_at=datetime.utcnow(),
    )
    db_session.add(subscriber)
    db_session.commit()
    subscriber_id = subscriber.id

    try:
        response = await client.post(
            f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=10"
        )
        assert response.status_code == 400
        assert "unsubscribed" in response.json()["detail"].lower()
    finally:
        db_session.delete(subscriber)
        db_session.commit()


@pytest.mark.asyncio
async def test_send_promo_code_already_used(client, db_session):
    """Should return 400 when promo code already used."""
    import secrets
    unique_suffix = secrets.token_hex(4)

    subscriber = MarketingSubscriber(
        first_name="Used",
        last_name="Promo",
        email=f"used-{unique_suffix}@test-promo.example.com",
        unsubscribe_token=f"used-token-{unique_suffix}",
        promo_code=f"TAG-USED-{unique_suffix[:8].upper()}",
        promo_code_sent=True,
        promo_code_used=True,
        promo_code_used_at=datetime.utcnow(),
    )
    db_session.add(subscriber)
    db_session.commit()
    subscriber_id = subscriber.id

    try:
        response = await client.post(
            f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=10"
        )
        assert response.status_code == 400
        assert "used" in response.json()["detail"].lower()
    finally:
        db_session.delete(subscriber)
        db_session.commit()


# =============================================================================
# Unit Tests - Promo Code Generation
# =============================================================================

class TestPromoCodeGeneration:
    """Unit tests for promo code generation."""

    def test_promo_code_format(self):
        """Promo codes should have correct format."""
        from email_service import generate_promo_code

        code = generate_promo_code()

        # Should be TAG-XXXX-XXXX format
        assert code.startswith("TAG-")
        parts = code.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4

    def test_promo_codes_are_unique(self):
        """Generated promo codes should be unique."""
        from email_service import generate_promo_code

        codes = [generate_promo_code() for _ in range(100)]

        # All codes should be unique
        assert len(codes) == len(set(codes))

    def test_promo_code_characters(self):
        """Promo codes should use uppercase alphanumeric characters."""
        from email_service import generate_promo_code

        for _ in range(10):
            code = generate_promo_code()
            # Remove TAG- prefix and dashes
            chars = code.replace("TAG-", "").replace("-", "")
            assert chars.isalnum()
            assert chars.isupper()
            # Should not contain confusing characters
            assert '0' not in chars
            assert 'O' not in chars
            assert 'I' not in chars
            assert '1' not in chars
            assert 'L' not in chars


# =============================================================================
# Unit Tests - Promo Code Validation
# =============================================================================

class TestPromoCodeValidation:
    """Tests for promo code validation during checkout."""

    def test_valid_10_percent_promo_code(self, db_session):
        """Should validate and apply 10% discount."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-valid10-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
            promo_code=f"TAG-V10-{unique_suffix[:8].upper()}",
            discount_percent=10,
            promo_code_sent=True,
        )
        db_session.add(subscriber)
        db_session.commit()

        try:
            # Query to validate code
            result = db_session.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code == subscriber.promo_code,
                MarketingSubscriber.promo_code_used == False,
                MarketingSubscriber.unsubscribed == False,
            ).first()

            assert result is not None
            assert result.discount_percent == 10
        finally:
            db_session.delete(subscriber)
            db_session.commit()

    def test_valid_100_percent_promo_code(self, db_session):
        """Should validate and apply 100% discount."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-valid100-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
            promo_code=f"TAG-V100-{unique_suffix[:8].upper()}",
            discount_percent=100,
            promo_code_sent=True,
        )
        db_session.add(subscriber)
        db_session.commit()

        try:
            result = db_session.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code == subscriber.promo_code,
                MarketingSubscriber.promo_code_used == False,
            ).first()

            assert result is not None
            assert result.discount_percent == 100
        finally:
            db_session.delete(subscriber)
            db_session.commit()

    def test_invalid_promo_code_not_found(self, db_session):
        """Should return None for non-existent promo code."""
        result = db_session.query(MarketingSubscriber).filter(
            MarketingSubscriber.promo_code == "TAG-FAKE-99999999"
        ).first()

        assert result is None

    def test_used_promo_code_rejected(self, db_session):
        """Should reject already-used promo codes."""
        import secrets
        unique_suffix = secrets.token_hex(4)

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-usedrej-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
            promo_code=f"TAG-USDR-{unique_suffix[:8].upper()}",
            discount_percent=10,
            promo_code_sent=True,
            promo_code_used=True,
            promo_code_used_at=datetime.utcnow(),
        )
        db_session.add(subscriber)
        db_session.commit()

        try:
            # Query with promo_code_used == False should not find it
            result = db_session.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code == subscriber.promo_code,
                MarketingSubscriber.promo_code_used == False,
            ).first()

            assert result is None
        finally:
            db_session.delete(subscriber)
            db_session.commit()

    def test_promo_code_case_sensitive(self, db_session):
        """Promo codes should be case-sensitive."""
        import secrets
        unique_suffix = secrets.token_hex(4)
        promo_code = f"TAG-CASE-{unique_suffix[:8].upper()}"

        subscriber = MarketingSubscriber(
            first_name="Test",
            last_name="User",
            email=f"test-case-{unique_suffix}@test-promo.example.com",
            unsubscribe_token=f"test-token-{unique_suffix}",
            promo_code=promo_code,
            discount_percent=10,
            promo_code_sent=True,
        )
        db_session.add(subscriber)
        db_session.commit()

        try:
            # Lowercase should not match
            result = db_session.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code == promo_code.lower()
            ).first()

            assert result is None

            # Exact case should match
            result = db_session.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code == promo_code
            ).first()

            assert result is not None
        finally:
            db_session.delete(subscriber)
            db_session.commit()


# =============================================================================
# Integration Tests - Full Flow
# =============================================================================

@pytest.mark.asyncio
async def test_full_promo_flow(client, db_session):
    """Test complete flow: subscribe -> send promo -> verify."""
    import secrets
    unique_suffix = secrets.token_hex(4)
    test_email = f"flow-{unique_suffix}@test-promo.example.com"

    # Step 1: Subscribe
    subscribe_response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "Flow",
            "last_name": "Test",
            "email": test_email,
            "source": "test",
        }
    )
    assert subscribe_response.status_code == 200
    assert subscribe_response.json()["success"] is True

    # Get subscriber ID
    db_session.expire_all()
    subscriber = db_session.query(MarketingSubscriber).filter(
        MarketingSubscriber.email == test_email
    ).first()
    subscriber_id = subscriber.id

    try:
        assert subscriber.promo_code is None

        # Step 2: Admin sends promo code
        with patch('email_service.send_promo_code_email') as mock_email:
            mock_email.return_value = True

            promo_response = await client.post(
                f"/api/admin/marketing-subscribers/{subscriber_id}/send-promo?discount_percent=10"
            )

        assert promo_response.status_code == 200
        promo_data = promo_response.json()
        assert promo_data["success"] is True
        assert promo_data["discount_percent"] == 10

        # Step 3: Verify subscriber has promo code
        db_session.expire_all()
        subscriber = db_session.query(MarketingSubscriber).filter(
            MarketingSubscriber.id == subscriber_id
        ).first()

        assert subscriber.promo_code == promo_data["promo_code"]
        assert subscriber.discount_percent == 10
        assert subscriber.promo_code_sent is True
        assert subscriber.promo_code_used is False

        # Step 4: Verify code appears in admin list
        list_response = await client.get("/api/admin/marketing-subscribers")

        subscribers = list_response.json()["subscribers"]
        flow_subscriber = next(
            (s for s in subscribers if s["email"] == test_email),
            None
        )
        assert flow_subscriber is not None
        assert flow_subscriber["promo_code"] == promo_data["promo_code"]
        assert flow_subscriber["discount_percent"] == 10
        assert flow_subscriber["promo_code_sent"] is True
    finally:
        # Cleanup
        subscriber = db_session.query(MarketingSubscriber).filter(
            MarketingSubscriber.id == subscriber_id
        ).first()
        if subscriber:
            db_session.delete(subscriber)
            db_session.commit()
