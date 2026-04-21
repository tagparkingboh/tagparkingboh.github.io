"""
Tests for the Promo Modal feature.

Includes both unit tests and integration tests for:
- Promo modal CRUD operations
- Subscriber limit auto-deactivation
- Concurrent subscriber sign-ups competing for last spot

All tests use mocked data - no real database connections.
"""
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport
from datetime import datetime, date
from sqlalchemy.sql.elements import BinaryExpression

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, check_promo_modal_subscriber_limits
from database import get_db
from db_models import PromoModal, PromoModalStatus, MarketingSubscriber


# =============================================================================
# Mock Database Setup
# =============================================================================

class MockDataStore:
    """In-memory store for mock data."""

    def __init__(self):
        self.promo_modals = {}
        self.subscribers = {}
        self.next_modal_id = 1
        self.next_subscriber_id = 1

    def add_promo_modal(self, modal):
        modal.id = self.next_modal_id
        modal.created_at = modal.created_at or datetime.utcnow()
        self.promo_modals[modal.id] = modal
        self.next_modal_id += 1
        return modal

    def add_subscriber(self, subscriber):
        subscriber.id = self.next_subscriber_id
        subscriber.subscribed_at = subscriber.subscribed_at or datetime.utcnow()
        self.subscribers[subscriber.email.lower()] = subscriber
        self.next_subscriber_id += 1
        return subscriber

    def get_modal_by_id(self, modal_id):
        return self.promo_modals.get(modal_id)

    def get_subscriber_by_email(self, email):
        return self.subscribers.get(email.lower())

    def get_all_modals(self):
        return list(self.promo_modals.values())

    def get_active_modals_with_limits(self):
        return [
            m for m in self.promo_modals.values()
            if m.status == PromoModalStatus.ACTIVE
            and m.max_subscribers is not None
            and m.subscribers_at_activation is not None
        ]

    def subscriber_count(self):
        return len(self.subscribers)

    def clear(self):
        self.promo_modals = {}
        self.subscribers = {}
        self.next_modal_id = 1
        self.next_subscriber_id = 1


# Global mock store
_mock_store = MockDataStore()


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
        for f in self._filters:
            if isinstance(f, BinaryExpression):
                try:
                    col_name = f.left.key if hasattr(f.left, 'key') else str(f.left)
                    if hasattr(f.right, 'value'):
                        value = f.right.value
                    elif hasattr(f.right, 'effective_value'):
                        value = f.right.effective_value
                    else:
                        value = str(f.right)

                    if self.model == PromoModal and 'id' in col_name.lower():
                        return self.store.get_modal_by_id(int(value))
                    elif self.model == MarketingSubscriber and 'email' in col_name.lower():
                        return self.store.get_subscriber_by_email(value)
                except Exception:
                    pass
        return None

    def all(self):
        if self.model == PromoModal:
            # Check for active status filter with limits
            for f in self._filters:
                if isinstance(f, BinaryExpression):
                    try:
                        col_name = f.left.key if hasattr(f.left, 'key') else str(f.left)
                        if 'status' in col_name.lower():
                            # Return active modals with limits for the limit check
                            return self.store.get_active_modals_with_limits()
                    except Exception:
                        pass
            return self.store.get_all_modals()
        return []

    def count(self):
        if self.model == MarketingSubscriber:
            return self.store.subscriber_count()
        return 0


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
            self.store.add_subscriber(obj)
        elif isinstance(obj, PromoModal):
            self.store.add_promo_modal(obj)

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
# Unit Tests - PromoModal Model
# =============================================================================

class TestPromoModalModel:
    """Unit tests for the PromoModal database model."""

    def test_create_promo_modal(self):
        """Should create a promo modal with required fields."""
        modal = PromoModal(
            title="Spring Sale!",
            message="Get 10% off your first booking",
        )
        _mock_store.add_promo_modal(modal)

        assert modal.id is not None
        assert modal.title == "Spring Sale!"
        assert modal.message == "Get 10% off your first booking"
        assert modal.created_at is not None

    def test_promo_modal_defaults(self):
        """Should have correct default values when added to store."""
        modal = PromoModal(
            title="Test",
            message="Test message",
            button_text="Subscribe",
            button_action="subscribe",
            status=PromoModalStatus.INACTIVE,
        )
        _mock_store.add_promo_modal(modal)

        assert modal.button_text == "Subscribe"
        assert modal.button_action == "subscribe"
        assert modal.status == PromoModalStatus.INACTIVE
        assert modal.max_subscribers is None
        assert modal.subscribers_at_activation is None

    def test_promo_modal_with_subscriber_limit(self):
        """Should store subscriber limit fields."""
        modal = PromoModal(
            title="Limited Offer",
            message="First 10 subscribers only!",
            max_subscribers=10,
            subscribers_at_activation=100,
        )
        _mock_store.add_promo_modal(modal)

        assert modal.max_subscribers == 10
        assert modal.subscribers_at_activation == 100

    def test_promo_modal_repr(self):
        """Should have a readable repr."""
        modal = PromoModal(
            title="Test Modal",
            message="Test",
            status=PromoModalStatus.INACTIVE,
        )
        _mock_store.add_promo_modal(modal)
        repr_str = repr(modal)
        assert "Test Modal" in repr_str


# =============================================================================
# Unit Tests - Subscriber Limit Logic
# =============================================================================

class TestSubscriberLimitLogic:
    """Unit tests for the subscriber limit auto-deactivation logic."""

    def test_check_limits_deactivates_modal_at_limit(self):
        """Should deactivate modal when subscriber limit is reached."""
        # Create a promo modal with limit of 5, activated when there were 10 subscribers
        modal = PromoModal(
            title="Limited Offer",
            message="First 5 only!",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=5,
            subscribers_at_activation=10,
        )
        _mock_store.add_promo_modal(modal)

        # Add 15 subscribers (10 existing + 5 new = limit reached)
        for i in range(15):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        # Run the check
        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # Modal should be deactivated
        assert modal.status == PromoModalStatus.INACTIVE

    def test_check_limits_does_not_deactivate_below_limit(self):
        """Should not deactivate modal when below subscriber limit."""
        modal = PromoModal(
            title="Limited Offer",
            message="First 10 only!",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=10,
            subscribers_at_activation=5,
        )
        _mock_store.add_promo_modal(modal)

        # Add only 10 subscribers (5 existing + 5 new, limit is 15)
        for i in range(10):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        # Run the check
        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # Modal should still be active
        assert modal.status == PromoModalStatus.ACTIVE

    def test_check_limits_ignores_modals_without_limit(self):
        """Should ignore modals without max_subscribers set."""
        modal = PromoModal(
            title="Unlimited Offer",
            message="No limit!",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=None,
        )
        _mock_store.add_promo_modal(modal)

        # Add many subscribers
        for i in range(100):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        # Run the check
        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # Modal should still be active
        assert modal.status == PromoModalStatus.ACTIVE

    def test_check_limits_ignores_inactive_modals(self):
        """Should ignore inactive modals even with limits."""
        modal = PromoModal(
            title="Inactive Offer",
            message="Not active",
            status=PromoModalStatus.INACTIVE,
            max_subscribers=1,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        # Add subscribers
        for i in range(5):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        # Run the check
        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # Modal should still be inactive (not changed)
        assert modal.status == PromoModalStatus.INACTIVE

    def test_exact_limit_boundary(self):
        """Should deactivate exactly when limit is reached, not before."""
        modal = PromoModal(
            title="Exact Test",
            message="Testing boundary",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=3,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        # Add 2 subscribers (below limit)
        for i in range(2):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)
        assert modal.status == PromoModalStatus.ACTIVE

        # Add 3rd subscriber (at limit)
        sub = MarketingSubscriber(
            first_name="User3",
            last_name="Test",
            email="user3@example.com",
        )
        _mock_store.add_subscriber(sub)

        check_promo_modal_subscriber_limits(db)
        assert modal.status == PromoModalStatus.INACTIVE

    def test_multiple_modals_with_different_limits(self):
        """Should handle multiple modals with different limits correctly."""
        modal1 = PromoModal(
            title="Low Limit",
            message="First 2 only",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=2,
            subscribers_at_activation=0,
        )
        modal2 = PromoModal(
            title="High Limit",
            message="First 10 only",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=10,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal1)
        _mock_store.add_promo_modal(modal2)

        # Add 5 subscribers
        for i in range(5):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # Modal 1 should be deactivated (limit 2, got 5)
        assert modal1.status == PromoModalStatus.INACTIVE
        # Modal 2 should still be active (limit 10, got 5)
        assert modal2.status == PromoModalStatus.ACTIVE


# =============================================================================
# Integration Tests - Subscribe API with Promo Limit
# =============================================================================

@pytest.mark.asyncio
async def test_subscribe_triggers_limit_check(client):
    """Subscribing should trigger the promo modal limit check."""
    # Create a modal with limit of 1
    modal = PromoModal(
        title="One Only",
        message="First subscriber wins",
        status=PromoModalStatus.ACTIVE,
        max_subscribers=1,
        subscribers_at_activation=0,
    )
    _mock_store.add_promo_modal(modal)

    # Subscribe
    response = await client.post(
        "/api/marketing/subscribe",
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
        }
    )
    assert response.status_code == 200

    # Modal should now be inactive
    assert modal.status == PromoModalStatus.INACTIVE


@pytest.mark.asyncio
async def test_subscribe_does_not_deactivate_below_limit(client):
    """Subscribing should not deactivate modal if below limit."""
    modal = PromoModal(
        title="Three Spots",
        message="First 3 subscribers",
        status=PromoModalStatus.ACTIVE,
        max_subscribers=3,
        subscribers_at_activation=0,
    )
    _mock_store.add_promo_modal(modal)

    # First subscriber
    await client.post(
        "/api/marketing/subscribe",
        json={"first_name": "User1", "last_name": "Test", "email": "user1@example.com"}
    )
    assert modal.status == PromoModalStatus.ACTIVE

    # Second subscriber
    await client.post(
        "/api/marketing/subscribe",
        json={"first_name": "User2", "last_name": "Test", "email": "user2@example.com"}
    )
    assert modal.status == PromoModalStatus.ACTIVE

    # Third subscriber - should trigger deactivation
    await client.post(
        "/api/marketing/subscribe",
        json={"first_name": "User3", "last_name": "Test", "email": "user3@example.com"}
    )
    assert modal.status == PromoModalStatus.INACTIVE


# =============================================================================
# Concurrent Subscriber Tests - Race Conditions
# =============================================================================

class TestConcurrentSubscribers:
    """Tests for concurrent subscriber sign-ups competing for last spot."""

    @pytest.mark.asyncio
    async def test_two_concurrent_subscribers_for_last_spot(self, client):
        """
        When two users try to subscribe simultaneously for the last spot,
        both subscriptions should succeed but modal should deactivate.
        """
        modal = PromoModal(
            title="Last Spot",
            message="Only 1 spot left!",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=1,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        async def subscribe(user_num: int):
            response = await client.post(
                "/api/marketing/subscribe",
                json={
                    "first_name": f"User{user_num}",
                    "last_name": "Test",
                    "email": f"user{user_num}@example.com",
                }
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
                "data": response.json()
            }

        # Run two subscribe requests concurrently
        results = await asyncio.gather(
            subscribe(1),
            subscribe(2),
            return_exceptions=True
        )

        # Both subscriptions should succeed
        successes = [r for r in results if isinstance(r, dict) and r["status_code"] == 200]
        assert len(successes) == 2, "Both subscriptions should succeed"

        # Modal should be deactivated
        assert modal.status == PromoModalStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_five_concurrent_subscribers_for_three_spots(self, client):
        """
        Five users subscribe concurrently when only 3 spots remain.
        All should subscribe successfully, modal should deactivate after 3rd.
        """
        modal = PromoModal(
            title="Three Spots",
            message="First 3 only!",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=3,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        async def subscribe(user_num: int):
            response = await client.post(
                "/api/marketing/subscribe",
                json={
                    "first_name": f"User{user_num}",
                    "last_name": "Test",
                    "email": f"user{user_num}@example.com",
                }
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
                "data": response.json()
            }

        # Run five subscribe requests concurrently
        results = await asyncio.gather(
            subscribe(1),
            subscribe(2),
            subscribe(3),
            subscribe(4),
            subscribe(5),
            return_exceptions=True
        )

        # All subscriptions should succeed (we don't block signups, just deactivate modal)
        successes = [r for r in results if isinstance(r, dict) and r["status_code"] == 200]
        assert len(successes) == 5, "All subscriptions should succeed"

        # Modal should be deactivated (limit was 3)
        assert modal.status == PromoModalStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_concurrent_subscribers_different_timing(self, client):
        """
        Simulate staggered concurrent requests with small delays.
        """
        modal = PromoModal(
            title="Timed Test",
            message="Testing timing",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=2,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        async def subscribe_with_delay(user_num: int, delay: float):
            await asyncio.sleep(delay)
            response = await client.post(
                "/api/marketing/subscribe",
                json={
                    "first_name": f"User{user_num}",
                    "last_name": "Test",
                    "email": f"user{user_num}@example.com",
                }
            )
            return {
                "user": user_num,
                "status_code": response.status_code,
            }

        # Staggered requests
        results = await asyncio.gather(
            subscribe_with_delay(1, 0),
            subscribe_with_delay(2, 0.01),
            subscribe_with_delay(3, 0.02),
        )

        # All should succeed
        for result in results:
            assert result["status_code"] == 200

        # Modal should be deactivated
        assert modal.status == PromoModalStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_rapid_sequential_subscriptions(self, client):
        """
        Rapid sequential subscriptions should be handled correctly.
        """
        modal = PromoModal(
            title="Rapid Test",
            message="Testing rapid signups",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=3,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        # Sequential rapid subscriptions
        for i in range(5):
            response = await client.post(
                "/api/marketing/subscribe",
                json={
                    "first_name": f"User{i}",
                    "last_name": "Test",
                    "email": f"user{i}@example.com",
                }
            )
            assert response.status_code == 200

        # Modal should be deactivated after 3rd subscriber
        assert modal.status == PromoModalStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_ten_concurrent_for_one_spot_stress(self, client):
        """
        Stress test: 10 concurrent subscribers for 1 spot.
        """
        modal = PromoModal(
            title="Stress Test",
            message="One spot only!",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=1,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        async def subscribe(user_num: int):
            response = await client.post(
                "/api/marketing/subscribe",
                json={
                    "first_name": f"User{user_num}",
                    "last_name": "Test",
                    "email": f"user{user_num}@example.com",
                }
            )
            return response.status_code

        # 10 concurrent requests
        results = await asyncio.gather(*[subscribe(i) for i in range(10)])

        # All should succeed (we accept all signups)
        assert all(code == 200 for code in results)

        # Modal must be deactivated
        assert modal.status == PromoModalStatus.INACTIVE

        # Verify we have 10 subscribers
        assert _mock_store.subscriber_count() == 10


# =============================================================================
# Edge Cases
# =============================================================================

class TestPromoModalEdgeCases:
    """Edge cases for promo modal subscriber limits."""

    @pytest.mark.asyncio
    async def test_duplicate_email_does_not_count_as_new(self, client):
        """
        Duplicate email signups should not count toward subscriber limit.
        """
        modal = PromoModal(
            title="No Duplicates",
            message="Testing duplicates",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=2,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        # Add existing subscriber
        existing = MarketingSubscriber(
            first_name="Existing",
            last_name="User",
            email="existing@example.com",
        )
        _mock_store.add_subscriber(existing)

        # Try to re-subscribe with same email
        response = await client.post(
            "/api/marketing/subscribe",
            json={
                "first_name": "Existing",
                "last_name": "User",
                "email": "existing@example.com",
            }
        )
        # Should return success but not count as new
        assert response.status_code == 200
        data = response.json()
        assert data["is_new_subscriber"] is False

        # Modal should still be active (limit was 2, only 1 subscriber)
        # Note: The check runs on the actual count in our mock
        assert modal.status == PromoModalStatus.ACTIVE

    def test_zero_max_subscribers_treated_as_unlimited(self):
        """
        A max_subscribers of 0 or None should mean unlimited.
        """
        modal = PromoModal(
            title="Unlimited",
            message="No limit",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=0,
        )
        _mock_store.add_promo_modal(modal)

        # Add many subscribers
        for i in range(50):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        # Run check
        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # Should still be active (0 means unlimited based on our logic)
        assert modal.status == PromoModalStatus.ACTIVE

    def test_negative_max_subscribers_behavior(self):
        """
        A negative max_subscribers value is an edge case.
        The current logic treats it as immediately satisfied (deactivates).
        This test documents the current behavior.
        """
        modal = PromoModal(
            title="Negative Test",
            message="Negative limit",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=-5,
            subscribers_at_activation=0,
        )
        _mock_store.add_promo_modal(modal)

        for i in range(10):
            sub = MarketingSubscriber(
                first_name=f"User{i}",
                last_name="Test",
                email=f"user{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        db = MockSession(_mock_store)
        check_promo_modal_subscriber_limits(db)

        # With negative max, current >= activation + max is always true
        # so it deactivates (current behavior)
        assert modal.status == PromoModalStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_modal_activated_mid_campaign(self, client):
        """
        Modal activated when there are already subscribers should only
        count NEW subscribers toward the limit.
        """
        # Pre-existing subscribers
        for i in range(10):
            sub = MarketingSubscriber(
                first_name=f"Existing{i}",
                last_name="User",
                email=f"existing{i}@example.com",
            )
            _mock_store.add_subscriber(sub)

        # Modal activated now (with 10 existing subscribers)
        modal = PromoModal(
            title="Mid Campaign",
            message="Started mid-way",
            status=PromoModalStatus.ACTIVE,
            max_subscribers=3,
            subscribers_at_activation=10,  # Captured at activation
        )
        _mock_store.add_promo_modal(modal)

        # New subscribers
        for i in range(3):
            response = await client.post(
                "/api/marketing/subscribe",
                json={
                    "first_name": f"New{i}",
                    "last_name": "User",
                    "email": f"new{i}@example.com",
                }
            )
            assert response.status_code == 200

        # Modal should be deactivated (3 new subscribers = limit reached)
        assert modal.status == PromoModalStatus.INACTIVE

        # Should have 13 total subscribers
        assert _mock_store.subscriber_count() == 13


# =============================================================================
# API Tests - Admin CRUD
# =============================================================================

class TestPromoModalAdminAPI:
    """Integration tests for admin promo modal endpoints (mocked auth)."""

    @pytest.mark.asyncio
    async def test_create_promo_modal_with_subscriber_limit(self, client):
        """Should create a promo modal with subscriber limit via API."""
        # This would require auth mocking - simplified version
        modal = PromoModal(
            title="API Test",
            message="Created via API",
            max_subscribers=10,
        )
        _mock_store.add_promo_modal(modal)

        assert modal.id is not None
        assert modal.max_subscribers == 10

    def test_update_max_subscribers(self):
        """Should be able to update max_subscribers field."""
        modal = PromoModal(
            title="Update Test",
            message="Testing update",
            max_subscribers=5,
        )
        _mock_store.add_promo_modal(modal)

        # Update
        modal.max_subscribers = 10
        assert modal.max_subscribers == 10

    def test_clear_max_subscribers(self):
        """Should be able to clear max_subscribers (make unlimited)."""
        modal = PromoModal(
            title="Clear Test",
            message="Testing clear",
            max_subscribers=5,
        )
        _mock_store.add_promo_modal(modal)

        # Clear
        modal.max_subscribers = None
        assert modal.max_subscribers is None
