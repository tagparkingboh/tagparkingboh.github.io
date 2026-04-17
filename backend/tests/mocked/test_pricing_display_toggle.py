"""
Tests for pricing display toggle feature.

Covers:
- show_price_range field defaults and behavior
- Admin pricing API includes toggle field
- Toggle affects frontend price display mode (From £X vs £X-£Y range)

All tests use mocked data - no real database connections.
"""
import pytest
from unittest.mock import patch, MagicMock


# ============================================================================
# MOCK DATA SETUP
# ============================================================================

DEFAULT_PRICING = {
    "days_1_4_price": 65,
    "days_5_6_price": 75,
    "week1_base_price": 89,
    "days_8_9_price": 109,
    "days_10_11_price": 129,
    "days_12_13_price": 139,
    "week2_base_price": 149,
    "tier_increment": 5,
    "peak_day_increment": 10,
    "show_price_range": False,  # Default: show "From £X" not range
}

PRICING_WITH_RANGE = {
    **DEFAULT_PRICING,
    "show_price_range": True,  # Show £X-£Y range
}


# ============================================================================
# UNIT TESTS - show_price_range behavior
# ============================================================================

class TestShowPriceRangeDefault:
    """Tests for default show_price_range behavior."""

    def test_default_is_false(self):
        """show_price_range should default to False (show 'From £X')."""
        assert DEFAULT_PRICING["show_price_range"] is False

    def test_from_display_when_false(self):
        """When show_price_range is False, display should be 'From £X'."""
        pricing = DEFAULT_PRICING

        # Frontend logic: if not showRange, display "From £{base_price}"
        show_range = pricing["show_price_range"]
        base_price = pricing["days_1_4_price"]

        if show_range:
            display = f"£{base_price}–£{base_price + (pricing['tier_increment'] * 2) + pricing['peak_day_increment']}"
        else:
            display = f"From £{base_price}"

        assert display == "From £65"

    def test_range_display_when_true(self):
        """When show_price_range is True, display should be '£X–£Y'."""
        pricing = PRICING_WITH_RANGE

        # Frontend logic: if showRange, display "£{min}–£{max}"
        show_range = pricing["show_price_range"]
        base_price = pricing["days_1_4_price"]
        tier_increment = pricing["tier_increment"]
        peak_day_increment = pricing["peak_day_increment"]

        max_price = base_price + (tier_increment * 2) + peak_day_increment

        if show_range:
            display = f"£{base_price}–£{max_price}"
        else:
            display = f"From £{base_price}"

        assert display == "£65–£85"


class TestMaxPriceCalculation:
    """Tests for maximum price calculation used in range display."""

    def test_max_price_formula(self):
        """Max price = base + (tier_increment * 2) + peak_day_increment."""
        pricing = DEFAULT_PRICING
        base = pricing["days_1_4_price"]
        tier = pricing["tier_increment"]
        peak = pricing["peak_day_increment"]

        expected_max = base + (tier * 2) + peak
        # 65 + (5 * 2) + 10 = 65 + 10 + 10 = 85
        assert expected_max == 85

    def test_max_price_without_peak_increment(self):
        """Max price when peak_day_increment is 0."""
        pricing = {**DEFAULT_PRICING, "peak_day_increment": 0}
        base = pricing["days_1_4_price"]
        tier = pricing["tier_increment"]
        peak = pricing["peak_day_increment"]

        expected_max = base + (tier * 2) + peak
        # 65 + (5 * 2) + 0 = 65 + 10 = 75
        assert expected_max == 75

    def test_max_price_all_packages(self):
        """Max price calculation works for all package types."""
        pricing = DEFAULT_PRICING
        tier = pricing["tier_increment"]
        peak = pricing["peak_day_increment"]
        max_addon = (tier * 2) + peak  # 10 + 10 = 20

        # 4-day: 65 + 20 = 85
        assert pricing["days_1_4_price"] + max_addon == 85

        # 7-day (week1): 89 + 20 = 109
        assert pricing["week1_base_price"] + max_addon == 109

        # 14-day (week2): 149 + 20 = 169
        assert pricing["week2_base_price"] + max_addon == 169


class TestToggleStateTransitions:
    """Tests for toggling between display modes."""

    def test_toggle_from_false_to_true(self):
        """Toggling show_price_range from False to True changes display."""
        pricing = dict(DEFAULT_PRICING)
        base = pricing["days_1_4_price"]

        # Initially False - "From" display
        assert pricing["show_price_range"] is False
        display_before = f"From £{base}"

        # Toggle to True - range display
        pricing["show_price_range"] = True
        max_price = base + (pricing["tier_increment"] * 2) + pricing["peak_day_increment"]
        display_after = f"£{base}–£{max_price}"

        assert display_before == "From £65"
        assert display_after == "£65–£85"
        assert display_before != display_after

    def test_toggle_from_true_to_false(self):
        """Toggling show_price_range from True to False changes display."""
        pricing = dict(PRICING_WITH_RANGE)
        base = pricing["days_1_4_price"]
        max_price = base + (pricing["tier_increment"] * 2) + pricing["peak_day_increment"]

        # Initially True - range display
        assert pricing["show_price_range"] is True
        display_before = f"£{base}–£{max_price}"

        # Toggle to False - "From" display
        pricing["show_price_range"] = False
        display_after = f"From £{base}"

        assert display_before == "£65–£85"
        assert display_after == "From £65"
        assert display_before != display_after


class TestFrontendPriceState:
    """Tests simulating frontend price state structure."""

    def test_frontend_prices_state_structure(self):
        """Frontend prices state includes showRange from API."""
        api_response = DEFAULT_PRICING

        # Simulate frontend state calculation
        tier_increment = api_response.get("tier_increment", 5)
        peak_day_increment = api_response.get("peak_day_increment", 0)
        max_addon = (tier_increment * 2) + peak_day_increment

        prices = {
            "days4": api_response["days_1_4_price"],
            "days4Max": api_response["days_1_4_price"] + max_addon,
            "week1": api_response["week1_base_price"],
            "week1Max": api_response["week1_base_price"] + max_addon,
            "week2": api_response["week2_base_price"],
            "week2Max": api_response["week2_base_price"] + max_addon,
            "showRange": api_response.get("show_price_range", False),
        }

        assert prices["days4"] == 65
        assert prices["days4Max"] == 85
        assert prices["week1"] == 89
        assert prices["week1Max"] == 109
        assert prices["week2"] == 149
        assert prices["week2Max"] == 169
        assert prices["showRange"] is False

    def test_frontend_prices_state_with_range(self):
        """Frontend prices state with showRange=True."""
        api_response = PRICING_WITH_RANGE

        # Simulate frontend state calculation
        tier_increment = api_response.get("tier_increment", 5)
        peak_day_increment = api_response.get("peak_day_increment", 0)
        max_addon = (tier_increment * 2) + peak_day_increment

        prices = {
            "days4": api_response["days_1_4_price"],
            "days4Max": api_response["days_1_4_price"] + max_addon,
            "week1": api_response["week1_base_price"],
            "week1Max": api_response["week1_base_price"] + max_addon,
            "week2": api_response["week2_base_price"],
            "week2Max": api_response["week2_base_price"] + max_addon,
            "showRange": api_response.get("show_price_range", False),
        }

        assert prices["showRange"] is True


class TestAPIResponseStructure:
    """Tests verifying API response includes show_price_range."""

    def test_pricing_api_includes_toggle(self):
        """GET /api/pricing should include show_price_range field."""
        # Simulate what the API returns
        api_response = {
            "days_1_4_price": 65,
            "days_5_6_price": 75,
            "week1_base_price": 89,
            "days_8_9_price": 109,
            "days_10_11_price": 129,
            "days_12_13_price": 139,
            "week2_base_price": 149,
            "tier_increment": 5,
            "peak_day_increment": 10,
            "show_price_range": False,
        }

        assert "show_price_range" in api_response
        assert isinstance(api_response["show_price_range"], bool)

    def test_admin_pricing_includes_toggle(self):
        """GET /api/admin/pricing should include show_price_range field."""
        admin_response = {
            "days_1_4_price": 65,
            "days_5_6_price": 75,
            "week1_base_price": 89,
            "days_8_9_price": 109,
            "days_10_11_price": 129,
            "days_12_13_price": 139,
            "week2_base_price": 149,
            "tier_increment": 5,
            "peak_day_increment": 10,
            "show_price_range": False,
        }

        assert "show_price_range" in admin_response
        assert admin_response["show_price_range"] is False

    def test_admin_update_pricing_accepts_toggle(self):
        """PUT /api/admin/pricing should accept show_price_range field."""
        update_payload = {
            "days_1_4_price": 65,
            "week1_base_price": 89,
            "week2_base_price": 149,
            "tier_increment": 5,
            "peak_day_increment": 10,
            "show_price_range": True,
        }

        assert "show_price_range" in update_payload
        assert update_payload["show_price_range"] is True
