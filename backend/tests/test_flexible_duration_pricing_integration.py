"""
Integration tests for flexible duration pricing.

Tests the full API flow for:
- GET /api/prices/durations endpoint (all duration x advance tier prices)
- Pricing settings CRUD endpoints via /api/admin/pricing
- Promo code validation and discount calculations

NOTE: The online booking flow tests are marked for future implementation.
The pricing functions are tested in unit tests. These integration tests
focus on API endpoints that use the new pricing system.
"""
import pytest
import pytest_asyncio
from datetime import date, timedelta
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from db_models import PricingSettings, MarketingSubscriber
from database import engine
from sqlalchemy.orm import sessionmaker

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
def db_session():
    """Create a database session for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Duration Prices API Tests (Public Endpoint)
# =============================================================================

class TestDurationPricesAPI:
    """Integration tests for GET /api/prices/durations endpoint."""

    @pytest.mark.asyncio
    async def test_get_duration_prices_returns_200(self, client):
        """GET /api/prices/durations should return 200 OK."""
        response = await client.get("/api/prices/durations")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_duration_prices_returns_all_tiers(self, client):
        """GET /api/prices/durations should return all duration tiers."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        # Should have all 7 duration tiers
        duration_tiers = ["1_4", "5_6", "7", "8_9", "10_11", "12_13", "14"]
        for tier in duration_tiers:
            assert tier in data, f"Missing duration tier: {tier}"

            # Each duration tier should have early, standard, late
            assert "early" in data[tier], f"Missing 'early' in tier {tier}"
            assert "standard" in data[tier], f"Missing 'standard' in tier {tier}"
            assert "late" in data[tier], f"Missing 'late' in tier {tier}"

    @pytest.mark.asyncio
    async def test_duration_prices_tier_increment_applied(self, client):
        """Verify tier increments are applied correctly to all durations."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        # With default tier_increment of £10:
        # For 7-day tier: early=79, standard=89, late=99
        assert data["7"]["early"] == 79.0
        assert data["7"]["standard"] == 89.0
        assert data["7"]["late"] == 99.0

        # For 14-day tier: early=140, standard=150, late=160
        assert data["14"]["early"] == 140.0
        assert data["14"]["standard"] == 150.0
        assert data["14"]["late"] == 160.0

    @pytest.mark.asyncio
    async def test_duration_prices_short_trip_tiers(self, client):
        """Verify short trip tier prices have correct structure."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        # 1-4 days: verify structure and increment pattern
        assert "1_4" in data
        assert data["1_4"]["early"] > 0
        assert data["1_4"]["standard"] > data["1_4"]["early"]
        assert data["1_4"]["late"] > data["1_4"]["standard"]

        # 5-6 days: verify structure and increment pattern
        assert "5_6" in data
        assert data["5_6"]["early"] > 0
        assert data["5_6"]["standard"] > data["5_6"]["early"]
        assert data["5_6"]["late"] > data["5_6"]["standard"]

    @pytest.mark.asyncio
    async def test_duration_prices_medium_trip_tiers(self, client):
        """Verify medium trip tier prices have correct structure."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        # 8-9 days: verify structure and increment pattern
        assert "8_9" in data
        assert data["8_9"]["early"] > 0
        assert data["8_9"]["standard"] > data["8_9"]["early"]
        assert data["8_9"]["late"] > data["8_9"]["standard"]

        # 10-11 days: verify structure and increment pattern
        assert "10_11" in data
        assert data["10_11"]["early"] > 0
        assert data["10_11"]["standard"] > data["10_11"]["early"]
        assert data["10_11"]["late"] > data["10_11"]["standard"]

    @pytest.mark.asyncio
    async def test_duration_prices_long_trip_tiers(self, client):
        """Verify long trip tier prices have correct structure."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        # 12-13 days: verify structure and increment pattern
        assert "12_13" in data
        assert data["12_13"]["early"] > 0
        assert data["12_13"]["standard"] > data["12_13"]["early"]
        assert data["12_13"]["late"] > data["12_13"]["standard"]


# =============================================================================
# Pricing Tiers API Tests (Legacy Endpoint)
# =============================================================================

class TestPricingTiersAPI:
    """Integration tests for GET /api/pricing/tiers endpoint (legacy)."""

    @pytest.mark.asyncio
    async def test_get_pricing_tiers_returns_200(self, client):
        """GET /api/pricing/tiers should return 200 OK."""
        response = await client.get("/api/pricing/tiers")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pricing_tiers_has_packages(self, client):
        """GET /api/pricing/tiers should return quick and longer packages."""
        response = await client.get("/api/pricing/tiers")
        data = response.json()

        assert "packages" in data
        assert "quick" in data["packages"]
        assert "longer" in data["packages"]

    @pytest.mark.asyncio
    async def test_get_pricing_tiers_quick_package_prices(self, client):
        """Quick package should have correct prices based on new 7-day base."""
        response = await client.get("/api/pricing/tiers")
        data = response.json()

        quick = data["packages"]["quick"]
        # 7-day (quick): early=79, standard=89, late=99
        assert quick["prices"]["early"] == 79.0
        assert quick["prices"]["standard"] == 89.0
        assert quick["prices"]["late"] == 99.0

    @pytest.mark.asyncio
    async def test_get_pricing_tiers_longer_package_prices(self, client):
        """Longer package should have correct prices based on 14-day tier."""
        response = await client.get("/api/pricing/tiers")
        data = response.json()

        longer = data["packages"]["longer"]
        # 14-day (longer): early=140, standard=150, late=160
        assert longer["prices"]["early"] == 140.0
        assert longer["prices"]["standard"] == 150.0
        assert longer["prices"]["late"] == 160.0


# =============================================================================
# Public Pricing API Tests
# =============================================================================

class TestPublicPricingAPI:
    """Integration tests for GET /api/pricing endpoint."""

    @pytest.mark.asyncio
    async def test_get_pricing_returns_200(self, client):
        """GET /api/pricing should return 200 OK."""
        response = await client.get("/api/pricing")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pricing_contains_base_prices(self, client):
        """GET /api/pricing should return base price fields."""
        response = await client.get("/api/pricing")
        data = response.json()

        # Should have week1 and week2 base prices
        assert "week1_base_price" in data
        assert "week2_base_price" in data

    @pytest.mark.asyncio
    async def test_get_pricing_contains_flexible_duration_prices(self, client):
        """GET /api/pricing should return all flexible duration price fields."""
        response = await client.get("/api/pricing")
        data = response.json()

        # Check all flexible duration fields
        assert "days_1_4_price" in data
        assert "days_5_6_price" in data
        assert "days_8_9_price" in data
        assert "days_10_11_price" in data
        assert "days_12_13_price" in data
        assert "tier_increment" in data


# =============================================================================
# Promo Code Integration Tests
# =============================================================================

class TestPromoCodeWithPricing:
    """Integration tests for promo codes with pricing."""

    _test_promo_codes = ["PRICING_TEST_10"]

    @pytest.fixture(autouse=True)
    def cleanup_test_data(self):
        """Clean up test data before and after each test."""
        db = TestSessionLocal()
        try:
            db.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code.in_(self._test_promo_codes)
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        yield

        db = TestSessionLocal()
        try:
            db.query(MarketingSubscriber).filter(
                MarketingSubscriber.promo_code.in_(self._test_promo_codes)
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _create_promo_subscriber(self, db, promo_code: str, email: str):
        """Create a subscriber with a promo code."""
        subscriber = MarketingSubscriber(
            first_name="Pricing",
            last_name="Test",
            email=email,
            promo_code=promo_code,
            promo_code_used=False,
        )
        db.add(subscriber)
        db.commit()
        return subscriber

    @pytest.mark.asyncio
    async def test_validate_promo_returns_10_percent_discount(self, client):
        """Valid promo code should return 10% discount."""
        db = TestSessionLocal()
        try:
            self._create_promo_subscriber(
                db, "PRICING_TEST_10", "pricing_test@example.com"
            )
        finally:
            db.close()

        response = await client.post(
            "/api/promo/validate",
            json={"code": "PRICING_TEST_10"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["discount_percent"] == 10


# =============================================================================
# Price Calculation Tests (Unit-level via API)
# =============================================================================

class TestPriceCalculationAPI:
    """Tests for price calculation via API endpoints."""

    @pytest.mark.asyncio
    async def test_calculate_price_quick_package(self, client):
        """POST /api/pricing/calculate for quick package (7 days)."""
        # Calculate price for quick package (7 days) booked 20 days ahead (early)
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=27)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Early tier for quick (7-day): £79
        assert data["price"] == 79.0
        assert data["package"] == "quick"

    @pytest.mark.asyncio
    async def test_calculate_price_longer_package(self, client):
        """POST /api/pricing/calculate for longer package (14 days)."""
        # Calculate price for longer package (14 days) booked 20 days ahead (early)
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=34)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Early tier for longer (14-day): £140
        assert data["price"] == 140.0
        assert data["package"] == "longer"

    @pytest.mark.asyncio
    async def test_calculate_price_standard_tier(self, client):
        """Calculate price for standard booking tier (7-13 days ahead)."""
        drop_off = (date.today() + timedelta(days=10)).isoformat()
        pickup = (date.today() + timedelta(days=17)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Standard tier for quick: £89 (£79 + £10)
        assert data["price"] == 89.0

    @pytest.mark.asyncio
    async def test_calculate_price_late_tier(self, client):
        """Calculate price for late booking tier (<7 days ahead)."""
        drop_off = (date.today() + timedelta(days=3)).isoformat()
        pickup = (date.today() + timedelta(days=10)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Late tier for quick: £99 (£79 + £20)
        assert data["price"] == 99.0


# =============================================================================
# Booking Service Function Tests via API
# =============================================================================

class TestBookingServiceFunctionsViaAPI:
    """Test booking service functions through the pricing API."""

    @pytest.mark.asyncio
    async def test_all_duration_tiers_have_consistent_increment(self, client):
        """All duration tiers should have consistent £10 increment between advance tiers."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        for tier_name, prices in data.items():
            # Standard should be early + 10
            assert prices["standard"] == prices["early"] + 10, \
                f"Tier {tier_name}: standard should be early + 10"
            # Late should be early + 20
            assert prices["late"] == prices["early"] + 20, \
                f"Tier {tier_name}: late should be early + 20"

    @pytest.mark.asyncio
    async def test_duration_prices_increase_with_trip_length(self, client):
        """Longer trips should generally cost more than shorter trips."""
        response = await client.get("/api/prices/durations")
        data = response.json()

        # Get early prices for all tiers
        prices_early = {
            "1_4": data["1_4"]["early"],
            "5_6": data["5_6"]["early"],
            "7": data["7"]["early"],
            "8_9": data["8_9"]["early"],
            "10_11": data["10_11"]["early"],
            "12_13": data["12_13"]["early"],
            "14": data["14"]["early"],
        }

        # Prices should generally increase (with some exceptions for value pricing)
        assert prices_early["1_4"] < prices_early["7"], "1-4 days should be cheaper than 7 days"
        assert prices_early["7"] < prices_early["14"], "7 days should be cheaper than 14 days"
        assert prices_early["8_9"] < prices_early["14"], "8-9 days should be cheaper than 14 days"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestPricingEdgeCases:
    """Edge case tests for pricing endpoints."""

    @pytest.mark.asyncio
    async def test_calculate_price_today_booking(self, client):
        """Price calculation for same-day booking should work (late tier)."""
        today = date.today().isoformat()
        pickup = (date.today() + timedelta(days=7)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": today,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Same-day is late tier: £99
        assert data["price"] == 99.0

    @pytest.mark.asyncio
    async def test_calculate_price_boundary_7_days(self, client):
        """Price calculation exactly 7 days ahead (boundary to standard tier)."""
        drop_off = (date.today() + timedelta(days=7)).isoformat()
        pickup = (date.today() + timedelta(days=14)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Exactly 7 days ahead is standard tier: £89
        assert data["price"] == 89.0

    @pytest.mark.asyncio
    async def test_calculate_price_boundary_14_days(self, client):
        """Price calculation exactly 14 days ahead (boundary to early tier)."""
        drop_off = (date.today() + timedelta(days=14)).isoformat()
        pickup = (date.today() + timedelta(days=21)).isoformat()

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        assert response.status_code == 200
        data = response.json()
        # Exactly 14 days ahead is early tier: £79
        assert data["price"] == 79.0

    @pytest.mark.asyncio
    async def test_invalid_duration_over_14_returns_error(self, client):
        """Duration over 14 days should return 400 error."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=35)).isoformat()  # 15 days - invalid

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        # Should return validation error for duration > 14 days
        assert response.status_code == 400
        assert "between 1 and 14 days" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_5_day_duration_is_valid(self, client):
        """5-day duration should now be valid (flexible pricing)."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=25)).isoformat()  # 5 days - now valid

        response = await client.post(
            "/api/pricing/calculate",
            json={
                "drop_off_date": drop_off,
                "pickup_date": pickup,
            }
        )

        # Should return 200 OK with price
        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 5
        assert data["price"] > 0


# =============================================================================
# Flexible Duration Pricing Tests
# =============================================================================

class TestFlexibleDurationPricing:
    """Tests for flexible duration pricing (1-14 days)."""

    @pytest.mark.asyncio
    async def test_3_day_trip_uses_1_4_tier(self, client):
        """3-day trip should use 1-4 day tier."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=23)).isoformat()  # 3 days

        response = await client.post(
            "/api/pricing/calculate",
            json={"drop_off_date": drop_off, "pickup_date": pickup}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 3
        assert data["package_name"] == "1-4 Days"
        assert data["price"] > 0

    @pytest.mark.asyncio
    async def test_6_day_trip_uses_5_6_tier(self, client):
        """6-day trip should use 5-6 day tier."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=26)).isoformat()  # 6 days

        response = await client.post(
            "/api/pricing/calculate",
            json={"drop_off_date": drop_off, "pickup_date": pickup}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 6
        assert data["package_name"] == "5-6 Days"
        assert data["price"] > 0

    @pytest.mark.asyncio
    async def test_9_day_trip_uses_8_9_tier(self, client):
        """9-day trip should use 8-9 day tier."""
        drop_off = (date.today() + timedelta(days=20)).isoformat()
        pickup = (date.today() + timedelta(days=29)).isoformat()  # 9 days

        response = await client.post(
            "/api/pricing/calculate",
            json={"drop_off_date": drop_off, "pickup_date": pickup}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["duration_days"] == 9
        assert data["package_name"] == "8-9 Days"
        assert data["price"] > 0

    @pytest.mark.skip(reason="Pending: Update online booking for flexible durations")
    @pytest.mark.asyncio
    async def test_free_promo_7_day_trip_is_free(self):
        """FREE promo on ≤7 day trip should be £0."""
        pass

    @pytest.mark.skip(reason="Pending: Update online booking for flexible durations")
    @pytest.mark.asyncio
    async def test_free_promo_10_day_trip_deducts_79(self):
        """FREE promo on 10-day trip should deduct £79 (7-day base)."""
        pass
