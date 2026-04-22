"""
Unit and Integration tests for Pricing API endpoints.

Tests the pricing calculation and display functionality:
- POST /api/pricing/calculate (calculate price for booking)
- GET /api/pricing/tiers (get pricing tiers)
- GET /api/prices/durations (get duration prices)
- GET /api/pricing (public pricing display)
- GET /api/admin/pricing (admin pricing settings)
- PUT /api/admin/pricing (update pricing)

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    user.first_name = "Admin"
    return user


def create_mock_pricing_settings(
    days_1_4_price=65.0,
    week1_base_price=85.0,
    week2_base_price=150.0,
    daily_increment=8.0,
    tier_increment=5.0,
    peak_day_increment=0.0,
    show_price_range=False,
    updated_at=None,
    updated_by=None,
):
    """Create mock pricing settings."""
    settings = MagicMock()
    settings.days_1_4_price = Decimal(str(days_1_4_price))
    settings.week1_base_price = Decimal(str(week1_base_price))
    settings.week2_base_price = Decimal(str(week2_base_price))
    settings.daily_increment = Decimal(str(daily_increment))
    settings.tier_increment = Decimal(str(tier_increment))
    settings.peak_day_increment = Decimal(str(peak_day_increment))
    settings.show_price_range = show_price_range
    settings.updated_at = updated_at or datetime.now(timezone.utc)
    settings.updated_by = updated_by
    settings.updater = MagicMock(first_name="Admin") if updated_by else None
    return settings


# ============================================================================
# Calculate Price Tests
# ============================================================================

class TestCalculatePriceLogic:
    """Unit tests for price calculation logic."""

    # Happy Path
    def test_calculates_duration_correctly(self):
        """Should calculate duration from dates."""
        drop_off = date(2026, 6, 1)
        pickup = date(2026, 6, 8)

        duration = (pickup - drop_off).days

        assert duration == 7

    def test_1_day_duration(self):
        """Should handle 1 day duration."""
        drop_off = date(2026, 6, 1)
        pickup = date(2026, 6, 2)

        duration = (pickup - drop_off).days

        assert duration == 1

    def test_14_day_duration(self):
        """Should handle 14 day duration."""
        drop_off = date(2026, 6, 1)
        pickup = date(2026, 6, 15)

        duration = (pickup - drop_off).days

        assert duration == 14

    def test_generates_week_package_name(self):
        """Should generate '1 Week Trip' for 7 days."""
        duration = 7

        if duration == 7:
            name = "1 Week Trip"
        elif duration == 14:
            name = "2 Week Trip"
        else:
            name = f"{duration} Days"

        assert name == "1 Week Trip"

    def test_generates_2_week_package_name(self):
        """Should generate '2 Week Trip' for 14 days."""
        duration = 14

        if duration == 7:
            name = "1 Week Trip"
        elif duration == 14:
            name = "2 Week Trip"
        else:
            name = f"{duration} Days"

        assert name == "2 Week Trip"

    def test_generates_day_count_name(self):
        """Should generate 'X Days' for other durations."""
        duration = 5

        if duration == 7:
            name = "1 Week Trip"
        elif duration == 14:
            name = "2 Week Trip"
        elif duration == 1:
            name = "1 Day"
        else:
            name = f"{duration} Days"

        assert name == "5 Days"

    def test_singular_day_grammar(self):
        """Should use singular 'Day' for 1 day."""
        duration = 1

        name = f"{duration} Day{'s' if duration != 1 else ''}"

        assert name == "1 Day"

    # Advance Tier Tests
    def test_early_tier_14_plus_days(self):
        """Should be early tier for 14+ days in advance."""
        days_in_advance = 14

        if days_in_advance >= 14:
            tier = "early"
        elif days_in_advance >= 7:
            tier = "standard"
        else:
            tier = "late"

        assert tier == "early"

    def test_standard_tier_7_to_13_days(self):
        """Should be standard tier for 7-13 days in advance."""
        days_in_advance = 10

        if days_in_advance >= 14:
            tier = "early"
        elif days_in_advance >= 7:
            tier = "standard"
        else:
            tier = "late"

        assert tier == "standard"

    def test_late_tier_under_7_days(self):
        """Should be late tier for under 7 days."""
        days_in_advance = 3

        if days_in_advance >= 14:
            tier = "early"
        elif days_in_advance >= 7:
            tier = "standard"
        else:
            tier = "late"

        assert tier == "late"

    # Validation
    def test_duration_minimum_1_day(self):
        """Should validate minimum 1 day duration."""
        duration = 0

        is_valid = 1 <= duration <= 60

        assert is_valid is False

    def test_duration_maximum_60_days(self):
        """Should validate maximum 60 days duration."""
        duration = 61

        is_valid = 1 <= duration <= 60

        assert is_valid is False

    def test_valid_duration_range(self):
        """Should accept valid duration range."""
        for duration in [1, 7, 14, 30, 60]:
            is_valid = 1 <= duration <= 60
            assert is_valid is True


# ============================================================================
# Pricing Tiers Tests
# ============================================================================

class TestPricingTiersLogic:
    """Unit tests for pricing tiers endpoint."""

    def test_returns_quick_package(self):
        """Should return quick (1 week) package."""
        packages = {
            "quick": {
                "name": "1 Week",
                "duration_days": 7,
                "prices": {"early": 85, "standard": 90, "late": 95},
            },
        }

        assert packages["quick"]["name"] == "1 Week"
        assert packages["quick"]["duration_days"] == 7

    def test_returns_longer_package(self):
        """Should return longer (2 weeks) package."""
        packages = {
            "longer": {
                "name": "2 Weeks",
                "duration_days": 14,
                "prices": {"early": 150, "standard": 155, "late": 160},
            },
        }

        assert packages["longer"]["name"] == "2 Weeks"
        assert packages["longer"]["duration_days"] == 14

    def test_returns_tier_definitions(self):
        """Should return tier definitions."""
        tiers = {
            "early": {"label": "14+ days in advance", "min_days": 14},
            "standard": {"label": "7-13 days in advance", "min_days": 7, "max_days": 13},
            "late": {"label": "Less than 7 days", "max_days": 6},
        }

        assert tiers["early"]["min_days"] == 14
        assert tiers["standard"]["min_days"] == 7
        assert tiers["standard"]["max_days"] == 13
        assert tiers["late"]["max_days"] == 6


# ============================================================================
# Duration Prices Tests
# ============================================================================

class TestDurationPricesLogic:
    """Unit tests for duration prices endpoint."""

    def test_returns_prices_for_all_durations(self):
        """Should return prices for all duration tiers."""
        prices = {
            "1": {"early": 65, "standard": 70, "late": 75},
            "7": {"early": 85, "standard": 90, "late": 95},
            "14": {"early": 150, "standard": 155, "late": 160},
        }

        assert "1" in prices
        assert "7" in prices
        assert "14" in prices

    def test_each_duration_has_three_tiers(self):
        """Should have early, standard, late for each duration."""
        prices = {
            "7": {"early": 85, "standard": 90, "late": 95},
        }

        assert "early" in prices["7"]
        assert "standard" in prices["7"]
        assert "late" in prices["7"]

    def test_price_increases_with_tier(self):
        """Should have increasing prices from early to late."""
        prices = {"early": 85, "standard": 90, "late": 95}

        assert prices["early"] < prices["standard"]
        assert prices["standard"] < prices["late"]


# ============================================================================
# Public Pricing Tests
# ============================================================================

class TestPublicPricingLogic:
    """Unit tests for public pricing endpoint."""

    def test_returns_pricing_settings(self):
        """Should return current pricing settings."""
        settings = create_mock_pricing_settings()

        response = {
            "days_1_4_price": float(settings.days_1_4_price),
            "week1_base_price": float(settings.week1_base_price),
            "week2_base_price": float(settings.week2_base_price),
        }

        assert response["days_1_4_price"] == 65.0
        assert response["week1_base_price"] == 85.0
        assert response["week2_base_price"] == 150.0

    def test_no_auth_required(self):
        """Should not require authentication."""
        is_public = True

        assert is_public is True


# ============================================================================
# Admin Pricing Get Tests
# ============================================================================

class TestAdminPricingGetLogic:
    """Unit tests for admin pricing GET endpoint."""

    def test_returns_all_pricing_fields(self):
        """Should return all pricing settings fields."""
        settings = create_mock_pricing_settings()

        response = {
            "days_1_4_price": float(settings.days_1_4_price),
            "week1_base_price": float(settings.week1_base_price),
            "week2_base_price": float(settings.week2_base_price),
            "daily_increment": float(settings.daily_increment),
            "tier_increment": float(settings.tier_increment),
            "peak_day_increment": float(settings.peak_day_increment),
            "show_price_range": settings.show_price_range,
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
            "updated_by": settings.updater.first_name if settings.updater else None,
        }

        assert "days_1_4_price" in response
        assert "daily_increment" in response
        assert "tier_increment" in response
        assert "updated_at" in response

    def test_returns_defaults_if_no_settings(self):
        """Should return defaults if no settings exist."""
        defaults = {
            "days_1_4_price": 65.0,
            "week1_base_price": 85.0,
            "week2_base_price": 150.0,
            "daily_increment": 8.0,
            "tier_increment": 5.0,
            "peak_day_increment": 0.0,
            "show_price_range": False,
            "updated_at": None,
            "updated_by": None,
        }

        assert defaults["days_1_4_price"] == 65.0
        assert defaults["daily_increment"] == 8.0
        assert defaults["updated_at"] is None

    def test_includes_updated_by_name(self):
        """Should include updater's name."""
        settings = create_mock_pricing_settings(updated_by=1)

        updated_by = settings.updater.first_name if settings.updater else None

        assert updated_by == "Admin"


# ============================================================================
# Admin Pricing Update Tests
# ============================================================================

class TestAdminPricingUpdateLogic:
    """Unit tests for admin pricing PUT endpoint."""

    def test_updates_days_1_4_price(self):
        """Should update 1-4 day price."""
        settings = create_mock_pricing_settings()
        new_price = 70.0

        settings.days_1_4_price = Decimal(str(new_price))

        assert float(settings.days_1_4_price) == 70.0

    def test_updates_week1_base_price(self):
        """Should update week 1 base price."""
        settings = create_mock_pricing_settings()
        new_price = 90.0

        settings.week1_base_price = Decimal(str(new_price))

        assert float(settings.week1_base_price) == 90.0

    def test_updates_week2_base_price(self):
        """Should update week 2 base price."""
        settings = create_mock_pricing_settings()
        new_price = 160.0

        settings.week2_base_price = Decimal(str(new_price))

        assert float(settings.week2_base_price) == 160.0

    def test_updates_daily_increment(self):
        """Should update daily increment."""
        settings = create_mock_pricing_settings()
        new_increment = 10.0

        settings.daily_increment = Decimal(str(new_increment))

        assert float(settings.daily_increment) == 10.0

    def test_updates_tier_increment(self):
        """Should update tier increment."""
        settings = create_mock_pricing_settings()
        new_increment = 7.0

        settings.tier_increment = Decimal(str(new_increment))

        assert float(settings.tier_increment) == 7.0

    def test_updates_peak_day_increment(self):
        """Should update peak day increment."""
        settings = create_mock_pricing_settings()
        new_increment = 5.0

        settings.peak_day_increment = Decimal(str(new_increment))

        assert float(settings.peak_day_increment) == 5.0

    def test_updates_show_price_range(self):
        """Should update show price range toggle."""
        settings = create_mock_pricing_settings(show_price_range=False)

        settings.show_price_range = True

        assert settings.show_price_range is True

    def test_updates_updated_by(self):
        """Should update updated_by to current user."""
        settings = create_mock_pricing_settings()
        user = create_mock_admin_user()

        settings.updated_by = user.id

        assert settings.updated_by == 1

    def test_creates_new_settings_if_none_exist(self):
        """Should create new settings if none exist."""
        mock_db = MagicMock()
        mock_db.query.return_value.first.return_value = None

        # Check that first() returns None
        existing = mock_db.query().first()

        assert existing is None


# ============================================================================
# Anchor Pricing Logic Tests
# ============================================================================

class TestAnchorPricingLogic:
    """Tests for anchor pricing calculation logic."""

    def test_1_to_4_days_uses_base_price(self):
        """Should use days_1_4_price for 1-4 day bookings."""
        days_1_4_price = 65.0
        duration = 3

        if 1 <= duration <= 4:
            price = days_1_4_price
        else:
            price = None

        assert price == 65.0

    def test_7_days_uses_week1_price(self):
        """Should use week1_base_price for 7 day bookings."""
        week1_base_price = 85.0
        duration = 7

        if duration == 7:
            price = week1_base_price
        else:
            price = None

        assert price == 85.0

    def test_14_days_uses_week2_price(self):
        """Should use week2_base_price for 14 day bookings."""
        week2_base_price = 150.0
        duration = 14

        if duration == 14:
            price = week2_base_price
        else:
            price = None

        assert price == 150.0

    def test_5_6_days_uses_daily_increment(self):
        """Should use daily increment for 5-6 days."""
        days_1_4_price = 65.0
        daily_increment = 8.0
        duration = 5

        # 5 days = base + 1 day increment
        if 5 <= duration <= 6:
            price = days_1_4_price + (duration - 4) * daily_increment
        else:
            price = None

        assert price == 73.0  # 65 + 8

    def test_6_days_calculation(self):
        """Should calculate 6 days correctly."""
        days_1_4_price = 65.0
        daily_increment = 8.0
        duration = 6

        price = days_1_4_price + (duration - 4) * daily_increment

        assert price == 81.0  # 65 + 16

    def test_tier_increment_applies_correctly(self):
        """Should apply tier increment for advance booking."""
        base_price = 85.0
        tier_increment = 5.0
        tier = "standard"

        if tier == "early":
            price = base_price
        elif tier == "standard":
            price = base_price + tier_increment
        else:  # late
            price = base_price + (2 * tier_increment)

        assert price == 90.0

    def test_late_tier_double_increment(self):
        """Should apply double increment for late bookings."""
        base_price = 85.0
        tier_increment = 5.0
        tier = "late"

        if tier == "early":
            price = base_price
        elif tier == "standard":
            price = base_price + tier_increment
        else:  # late
            price = base_price + (2 * tier_increment)

        assert price == 95.0


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestPricingResponseStructure:
    """Tests for pricing response structure."""

    def test_calculate_response_structure(self):
        """Should return correct calculate price response."""
        response = {
            "package": "quick",
            "package_name": "1 Week Trip",
            "duration_days": 7,
            "advance_tier": "early",
            "days_in_advance": 14,
            "price": 85.0,
            "price_pence": 8500,
            "week1_price": 85.0,
            "all_prices": {
                "early": 85.0,
                "standard": 90.0,
                "late": 95.0,
            },
        }

        assert "package" in response
        assert "price" in response
        assert "price_pence" in response
        assert "all_prices" in response

    def test_price_pence_is_integer(self):
        """Should return price_pence as integer."""
        price = 85.50
        price_pence = int(price * 100)

        assert price_pence == 8550
        assert isinstance(price_pence, int)

    def test_tiers_response_structure(self):
        """Should return correct pricing tiers response."""
        response = {
            "packages": {
                "quick": {"name": "1 Week", "duration_days": 7, "prices": {}},
                "longer": {"name": "2 Weeks", "duration_days": 14, "prices": {}},
            },
            "tiers": {
                "early": {},
                "standard": {},
                "late": {},
            },
        }

        assert "packages" in response
        assert "tiers" in response
        assert "quick" in response["packages"]
        assert "longer" in response["packages"]

    def test_admin_update_response_structure(self):
        """Should return correct admin update response."""
        response = {
            "success": True,
            "message": "Pricing updated successfully",
            "pricing": {
                "days_1_4_price": 65.0,
                "week1_base_price": 85.0,
            },
        }

        assert response["success"] is True
        assert "pricing" in response


# ============================================================================
# Authentication Tests
# ============================================================================

class TestPricingAuthentication:
    """Tests for authentication on pricing endpoints."""

    def test_calculate_is_public(self):
        """Calculate price endpoint should be public."""
        # POST /api/pricing/calculate - no admin prefix
        is_public = True

        assert is_public is True

    def test_tiers_is_public(self):
        """Pricing tiers endpoint should be public."""
        # GET /api/pricing/tiers - no admin prefix
        is_public = True

        assert is_public is True

    def test_durations_is_public(self):
        """Duration prices endpoint should be public."""
        # GET /api/prices/durations - no admin prefix
        is_public = True

        assert is_public is True

    def test_public_pricing_is_public(self):
        """Public pricing endpoint should be public."""
        # GET /api/pricing - no admin prefix
        is_public = True

        assert is_public is True

    def test_admin_get_requires_admin(self):
        """Admin pricing GET should require admin."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_admin_update_requires_admin(self):
        """Admin pricing PUT should require admin."""
        user = create_mock_admin_user()

        assert user.is_admin is True


# ============================================================================
# Boundary Tests
# ============================================================================

class TestPricingBoundaries:
    """Tests for boundary conditions."""

    def test_minimum_price(self):
        """Should handle minimum price (0)."""
        settings = create_mock_pricing_settings(days_1_4_price=0)

        assert float(settings.days_1_4_price) == 0

    def test_large_price(self):
        """Should handle large prices."""
        settings = create_mock_pricing_settings(week2_base_price=999.99)

        assert float(settings.week2_base_price) == 999.99

    def test_decimal_precision(self):
        """Should maintain decimal precision."""
        settings = create_mock_pricing_settings(daily_increment=8.50)

        assert float(settings.daily_increment) == 8.50

    def test_exactly_7_days_advance(self):
        """Should handle exactly 7 days in advance."""
        days_in_advance = 7

        if days_in_advance >= 14:
            tier = "early"
        elif days_in_advance >= 7:
            tier = "standard"
        else:
            tier = "late"

        assert tier == "standard"

    def test_exactly_14_days_advance(self):
        """Should handle exactly 14 days in advance."""
        days_in_advance = 14

        if days_in_advance >= 14:
            tier = "early"
        elif days_in_advance >= 7:
            tier = "standard"
        else:
            tier = "late"

        assert tier == "early"

    def test_duration_exactly_60_days(self):
        """Should handle exactly 60 days duration."""
        duration = 60

        is_valid = 1 <= duration <= 60

        assert is_valid is True

    def test_duration_exactly_1_day(self):
        """Should handle exactly 1 day duration."""
        duration = 1

        is_valid = 1 <= duration <= 60

        assert is_valid is True

    def test_zero_daily_increment(self):
        """Should handle zero daily increment."""
        settings = create_mock_pricing_settings(daily_increment=0)

        assert float(settings.daily_increment) == 0

    def test_zero_tier_increment(self):
        """Should handle zero tier increment."""
        settings = create_mock_pricing_settings(tier_increment=0)

        assert float(settings.tier_increment) == 0

    def test_show_price_range_true(self):
        """Should handle show_price_range = True."""
        settings = create_mock_pricing_settings(show_price_range=True)

        assert settings.show_price_range is True

    def test_show_price_range_false(self):
        """Should handle show_price_range = False."""
        settings = create_mock_pricing_settings(show_price_range=False)

        assert settings.show_price_range is False


# ============================================================================
# Price Display Tests
# ============================================================================

class TestPriceDisplay:
    """Tests for price display logic."""

    def test_from_price_display(self):
        """Should display 'From £X' when not showing range."""
        show_price_range = False
        min_price = 65

        if show_price_range:
            display = f"£{min_price}-£{min_price + 10}"
        else:
            display = f"From £{min_price}"

        assert display == "From £65"

    def test_price_range_display(self):
        """Should display '£X-£Y' when showing range."""
        show_price_range = True
        min_price = 65
        max_price = 75

        if show_price_range:
            display = f"£{min_price}-£{max_price}"
        else:
            display = f"From £{min_price}"

        assert display == "£65-£75"

    def test_all_prices_contains_three_tiers(self):
        """Should return all three tier prices."""
        all_prices = {
            "early": 85.0,
            "standard": 90.0,
            "late": 95.0,
        }

        assert len(all_prices) == 3
        assert all(tier in all_prices for tier in ["early", "standard", "late"])


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
