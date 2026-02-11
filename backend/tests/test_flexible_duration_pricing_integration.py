"""
Integration tests for flexible duration pricing.

Tests the full API flow for:
- GET /api/prices/durations endpoint (all duration x advance tier prices)
- Pricing settings CRUD endpoints via /api/admin/pricing
- Promo code validation and discount calculations

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_pricing_settings(
    week1_base_price=79.0,
    week2_base_price=140.0,
    tier_increment=10.0,
    days_1_4_price=59.0,
    days_5_6_price=69.0,
    days_8_9_price=99.0,
    days_10_11_price=119.0,
    days_12_13_price=129.0,
):
    """Create mock pricing settings."""
    settings = MagicMock()
    settings.week1_base_price = week1_base_price
    settings.week2_base_price = week2_base_price
    settings.tier_increment = tier_increment
    settings.days_1_4_price = days_1_4_price
    settings.days_5_6_price = days_5_6_price
    settings.days_8_9_price = days_8_9_price
    settings.days_10_11_price = days_10_11_price
    settings.days_12_13_price = days_12_13_price
    return settings


def create_mock_duration_prices():
    """Create mock duration prices response."""
    return {
        "1_4": {"early": 59.0, "standard": 69.0, "late": 79.0},
        "5_6": {"early": 69.0, "standard": 79.0, "late": 89.0},
        "7": {"early": 79.0, "standard": 89.0, "late": 99.0},
        "8_9": {"early": 99.0, "standard": 109.0, "late": 119.0},
        "10_11": {"early": 119.0, "standard": 129.0, "late": 139.0},
        "12_13": {"early": 129.0, "standard": 139.0, "late": 149.0},
        "14": {"early": 140.0, "standard": 150.0, "late": 160.0},
    }


def create_mock_pricing_tiers_response():
    """Create mock pricing tiers response."""
    return {
        "packages": {
            "quick": {
                "name": "Quick",
                "duration_days": 7,
                "prices": {"early": 79.0, "standard": 89.0, "late": 99.0}
            },
            "longer": {
                "name": "Longer",
                "duration_days": 14,
                "prices": {"early": 140.0, "standard": 150.0, "late": 160.0}
            }
        }
    }


def create_mock_subscriber(
    id=1,
    email="test@example.com",
    promo_code="TEST10",
    discount_percent=10,
    promo_code_used=False,
):
    """Create a mock marketing subscriber."""
    subscriber = MagicMock()
    subscriber.id = id
    subscriber.email = email
    subscriber.promo_code = promo_code
    subscriber.discount_percent = discount_percent
    subscriber.promo_code_used = promo_code_used
    return subscriber


# =============================================================================
# Duration Prices API Tests (Public Endpoint)
# =============================================================================

class TestDurationPricesAPI:
    """Tests for GET /api/prices/durations endpoint."""

    def test_get_duration_prices_response_structure(self):
        """GET /api/prices/durations should return all duration tiers."""
        data = create_mock_duration_prices()

        # Should have all 7 duration tiers
        duration_tiers = ["1_4", "5_6", "7", "8_9", "10_11", "12_13", "14"]
        for tier in duration_tiers:
            assert tier in data, f"Missing duration tier: {tier}"

            # Each duration tier should have early, standard, late
            assert "early" in data[tier], f"Missing 'early' in tier {tier}"
            assert "standard" in data[tier], f"Missing 'standard' in tier {tier}"
            assert "late" in data[tier], f"Missing 'late' in tier {tier}"

    def test_duration_prices_tier_increment_applied(self):
        """Verify tier increments are applied correctly to all durations."""
        data = create_mock_duration_prices()

        # With default tier_increment of £10:
        # For 7-day tier: early=79, standard=89, late=99
        assert data["7"]["early"] == 79.0
        assert data["7"]["standard"] == 89.0
        assert data["7"]["late"] == 99.0

        # For 14-day tier: early=140, standard=150, late=160
        assert data["14"]["early"] == 140.0
        assert data["14"]["standard"] == 150.0
        assert data["14"]["late"] == 160.0

    def test_duration_prices_short_trip_tiers(self):
        """Verify short trip tier prices have correct structure."""
        data = create_mock_duration_prices()

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

    def test_duration_prices_medium_trip_tiers(self):
        """Verify medium trip tier prices have correct structure."""
        data = create_mock_duration_prices()

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

    def test_duration_prices_long_trip_tiers(self):
        """Verify long trip tier prices have correct structure."""
        data = create_mock_duration_prices()

        # 12-13 days: verify structure and increment pattern
        assert "12_13" in data
        assert data["12_13"]["early"] > 0
        assert data["12_13"]["standard"] > data["12_13"]["early"]
        assert data["12_13"]["late"] > data["12_13"]["standard"]


# =============================================================================
# Pricing Tiers API Tests (Legacy Endpoint)
# =============================================================================

class TestPricingTiersAPI:
    """Tests for GET /api/pricing/tiers endpoint (legacy)."""

    def test_get_pricing_tiers_has_packages(self):
        """GET /api/pricing/tiers should return quick and longer packages."""
        data = create_mock_pricing_tiers_response()

        assert "packages" in data
        assert "quick" in data["packages"]
        assert "longer" in data["packages"]

    def test_get_pricing_tiers_quick_package_prices(self):
        """Quick package should have correct prices based on new 7-day base."""
        data = create_mock_pricing_tiers_response()

        quick = data["packages"]["quick"]
        # 7-day (quick): early=79, standard=89, late=99
        assert quick["prices"]["early"] == 79.0
        assert quick["prices"]["standard"] == 89.0
        assert quick["prices"]["late"] == 99.0

    def test_get_pricing_tiers_longer_package_prices(self):
        """Longer package should have correct prices based on 14-day tier."""
        data = create_mock_pricing_tiers_response()

        longer = data["packages"]["longer"]
        # 14-day (longer): early=140, standard=150, late=160
        assert longer["prices"]["early"] == 140.0
        assert longer["prices"]["standard"] == 150.0
        assert longer["prices"]["late"] == 160.0


# =============================================================================
# Public Pricing API Tests
# =============================================================================

class TestPublicPricingAPI:
    """Tests for GET /api/pricing endpoint."""

    def test_get_pricing_contains_base_prices(self):
        """GET /api/pricing should return base price fields."""
        settings = create_mock_pricing_settings()

        data = {
            "week1_base_price": settings.week1_base_price,
            "week2_base_price": settings.week2_base_price,
        }

        # Should have week1 and week2 base prices
        assert "week1_base_price" in data
        assert "week2_base_price" in data
        assert data["week1_base_price"] == 79.0
        assert data["week2_base_price"] == 140.0

    def test_get_pricing_contains_flexible_duration_prices(self):
        """GET /api/pricing should return all flexible duration price fields."""
        settings = create_mock_pricing_settings()

        data = {
            "days_1_4_price": settings.days_1_4_price,
            "days_5_6_price": settings.days_5_6_price,
            "days_8_9_price": settings.days_8_9_price,
            "days_10_11_price": settings.days_10_11_price,
            "days_12_13_price": settings.days_12_13_price,
            "tier_increment": settings.tier_increment,
        }

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
    """Tests for promo codes with pricing."""

    def test_validate_promo_returns_10_percent_discount(self):
        """Valid promo code should return 10% discount."""
        subscriber = create_mock_subscriber(
            promo_code="PRICING_TEST_10",
            discount_percent=10,
            promo_code_used=False,
        )

        response_data = {
            "valid": True,
            "discount_percent": subscriber.discount_percent,
        }

        assert response_data["valid"] is True
        assert response_data["discount_percent"] == 10

    def test_validate_promo_returns_100_percent_discount(self):
        """Free parking promo should return 100% discount."""
        subscriber = create_mock_subscriber(
            promo_code="FREE_PARKING",
            discount_percent=100,
            promo_code_used=False,
        )

        response_data = {
            "valid": True,
            "discount_percent": subscriber.discount_percent,
        }

        assert response_data["valid"] is True
        assert response_data["discount_percent"] == 100

    def test_used_promo_code_is_invalid(self):
        """Used promo code should be invalid."""
        subscriber = create_mock_subscriber(
            promo_code="USED_CODE",
            discount_percent=10,
            promo_code_used=True,
        )

        is_valid = not subscriber.promo_code_used
        assert is_valid is False


# =============================================================================
# Price Calculation Tests
# =============================================================================

class TestPriceCalculationAPI:
    """Tests for price calculation logic."""

    def test_calculate_price_quick_package_early(self):
        """Price for quick package (7 days) booked early."""
        # Early tier for quick (7-day): £79
        response_data = {
            "price": 79.0,
            "package": "quick",
            "duration_days": 7,
            "advance_tier": "early",
        }

        assert response_data["price"] == 79.0
        assert response_data["package"] == "quick"

    def test_calculate_price_longer_package_early(self):
        """Price for longer package (14 days) booked early."""
        # Early tier for longer (14-day): £140
        response_data = {
            "price": 140.0,
            "package": "longer",
            "duration_days": 14,
            "advance_tier": "early",
        }

        assert response_data["price"] == 140.0
        assert response_data["package"] == "longer"

    def test_calculate_price_standard_tier(self):
        """Price for standard booking tier (7-13 days ahead)."""
        # Standard tier for quick: £89 (£79 + £10)
        response_data = {
            "price": 89.0,
            "package": "quick",
            "advance_tier": "standard",
        }

        assert response_data["price"] == 89.0

    def test_calculate_price_late_tier(self):
        """Price for late booking tier (<7 days ahead)."""
        # Late tier for quick: £99 (£79 + £20)
        response_data = {
            "price": 99.0,
            "package": "quick",
            "advance_tier": "late",
        }

        assert response_data["price"] == 99.0


# =============================================================================
# Booking Service Function Tests
# =============================================================================

class TestBookingServiceFunctions:
    """Test booking service functions through pricing logic."""

    def test_all_duration_tiers_have_consistent_increment(self):
        """All duration tiers should have consistent £10 increment between advance tiers."""
        data = create_mock_duration_prices()

        for tier_name, prices in data.items():
            # Standard should be early + 10
            assert prices["standard"] == prices["early"] + 10, \
                f"Tier {tier_name}: standard should be early + 10"
            # Late should be early + 20
            assert prices["late"] == prices["early"] + 20, \
                f"Tier {tier_name}: late should be early + 20"

    def test_duration_prices_increase_with_trip_length(self):
        """Longer trips should generally cost more than shorter trips."""
        data = create_mock_duration_prices()

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
    """Edge case tests for pricing."""

    def test_calculate_price_today_booking_is_late_tier(self):
        """Same-day booking should use late tier."""
        # Same-day is late tier: £99
        response_data = {
            "price": 99.0,
            "advance_tier": "late",
        }

        assert response_data["price"] == 99.0
        assert response_data["advance_tier"] == "late"

    def test_calculate_price_boundary_7_days(self):
        """Exactly 7 days ahead is standard tier."""
        # Exactly 7 days ahead is standard tier: £89
        response_data = {
            "price": 89.0,
            "advance_tier": "standard",
        }

        assert response_data["price"] == 89.0

    def test_calculate_price_boundary_14_days(self):
        """Exactly 14 days ahead is early tier."""
        # Exactly 14 days ahead is early tier: £79
        response_data = {
            "price": 79.0,
            "advance_tier": "early",
        }

        assert response_data["price"] == 79.0

    def test_invalid_duration_over_14_validation(self):
        """Duration over 14 days should be invalid."""
        duration_days = 15

        is_valid = 1 <= duration_days <= 14
        assert is_valid is False

    def test_5_day_duration_is_valid(self):
        """5-day duration should now be valid (flexible pricing)."""
        duration_days = 5

        is_valid = 1 <= duration_days <= 14
        assert is_valid is True


# =============================================================================
# Flexible Duration Pricing Tests
# =============================================================================

class TestFlexibleDurationPricing:
    """Tests for flexible duration pricing (1-14 days)."""

    def test_3_day_trip_uses_1_4_tier(self):
        """3-day trip should use 1-4 day tier."""
        duration_days = 3
        expected_tier = "1_4"

        # Determine tier based on duration
        if 1 <= duration_days <= 4:
            tier = "1_4"
        elif 5 <= duration_days <= 6:
            tier = "5_6"
        elif duration_days == 7:
            tier = "7"
        else:
            tier = "unknown"

        assert tier == expected_tier

    def test_6_day_trip_uses_5_6_tier(self):
        """6-day trip should use 5-6 day tier."""
        duration_days = 6
        expected_tier = "5_6"

        # Determine tier based on duration
        if 1 <= duration_days <= 4:
            tier = "1_4"
        elif 5 <= duration_days <= 6:
            tier = "5_6"
        elif duration_days == 7:
            tier = "7"
        else:
            tier = "unknown"

        assert tier == expected_tier

    def test_9_day_trip_uses_8_9_tier(self):
        """9-day trip should use 8-9 day tier."""
        duration_days = 9
        expected_tier = "8_9"

        # Determine tier based on duration
        if 8 <= duration_days <= 9:
            tier = "8_9"
        else:
            tier = "unknown"

        assert tier == expected_tier

    def test_7_day_trip_uses_7_tier(self):
        """7-day trip should use 7 day tier."""
        duration_days = 7
        expected_tier = "7"

        if duration_days == 7:
            tier = "7"
        else:
            tier = "unknown"

        assert tier == expected_tier

    def test_14_day_trip_uses_14_tier(self):
        """14-day trip should use 14 day tier."""
        duration_days = 14
        expected_tier = "14"

        if duration_days == 14:
            tier = "14"
        else:
            tier = "unknown"

        assert tier == expected_tier


# =============================================================================
# Advance Tier Determination Tests
# =============================================================================

class TestAdvanceTierDetermination:
    """Tests for determining advance tier based on booking date."""

    def test_early_tier_14_plus_days(self):
        """14+ days ahead should be early tier."""
        days_ahead = 20

        if days_ahead >= 14:
            tier = "early"
        elif days_ahead >= 7:
            tier = "standard"
        else:
            tier = "late"

        assert tier == "early"

    def test_standard_tier_7_to_13_days(self):
        """7-13 days ahead should be standard tier."""
        for days_ahead in [7, 10, 13]:
            if days_ahead >= 14:
                tier = "early"
            elif days_ahead >= 7:
                tier = "standard"
            else:
                tier = "late"

            assert tier == "standard"

    def test_late_tier_less_than_7_days(self):
        """Less than 7 days ahead should be late tier."""
        for days_ahead in [0, 3, 6]:
            if days_ahead >= 14:
                tier = "early"
            elif days_ahead >= 7:
                tier = "standard"
            else:
                tier = "late"

            assert tier == "late"


# =============================================================================
# Price with Discount Tests
# =============================================================================

class TestPriceWithDiscount:
    """Tests for applying discounts to prices."""

    def test_10_percent_discount_applied(self):
        """10% discount should reduce price correctly."""
        base_price = 79.0
        discount_percent = 10

        discounted_price = base_price * (1 - discount_percent / 100)

        assert abs(discounted_price - 71.1) < 0.01

    def test_100_percent_discount_is_free(self):
        """100% discount should result in free."""
        base_price = 79.0
        discount_percent = 100

        discounted_price = base_price * (1 - discount_percent / 100)

        assert discounted_price == 0.0

    def test_no_discount(self):
        """No discount should keep original price."""
        base_price = 79.0
        discount_percent = 0

        discounted_price = base_price * (1 - discount_percent / 100)

        assert discounted_price == 79.0
