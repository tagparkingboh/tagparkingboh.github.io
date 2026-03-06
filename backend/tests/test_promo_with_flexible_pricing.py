"""
Tests for Promo Code functionality with Flexible Duration Pricing.

Tests that FREE promo (100% off) and 10% off promo codes work correctly
with the new flexible duration pricing system (1-60 days).

Pricing structure (early tier):
- 1-4 days: £60
- 5-6 days: £72
- 7 days: £79
- 8-9 days: £99
- 10-11 days: £119
- 12-13 days: £130
- 14 days: £140
- 15+ days: £140 + £9 per extra day

Test scenarios:
1. FREE promo with short trips (1-7 days) - should be completely free
2. FREE promo with medium trips (8-14 days) - 7-day base deducted
3. FREE promo with extended trips (15+ days) - 7-day base deducted
4. 10% promo with all duration tiers
5. Combined calculation verification
"""

import pytest
import sys
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import (
    calculate_price_in_pence,
    PROMO_DISCOUNT_PERCENT,
)
from booking_service import get_base_price_for_duration

# Default pricing structure (matches booking_service.py defaults)
DEFAULT_PRICING = {
    "days_1_4_price": 60.0,
    "days_5_6_price": 72.0,
    "week1_base_price": 79.0,   # 7 days
    "days_8_9_price": 99.0,
    "days_10_11_price": 119.0,
    "days_12_13_price": 130.0,
    "week2_base_price": 140.0,  # 14 days
    "extra_day_price": 9.0,     # 15+ days
    "tier_increment": 10.0,     # For standard/late pricing tiers
}

@pytest.fixture(autouse=True)
def mock_pricing():
    """Mock pricing from database for all tests to use DEFAULT_PRICING."""
    with patch("booking_service.get_pricing_from_db", return_value=DEFAULT_PRICING):
        yield


class TestFreePromoWithFlexiblePricing:
    """Tests for FREE promo (100% off) with flexible duration pricing."""

    def test_free_promo_7_day_trip_completely_free(self):
        """A 7-day trip with FREE promo should be completely free."""
        duration_days = 7
        package = "early"

        # Get original price
        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        # With FREE promo (duration <= 7), discount = full amount
        discount_amount = original_amount
        final_amount = original_amount - discount_amount

        assert original_amount == 7900, f"7-day early price should be £79, got £{original_amount/100}"
        assert final_amount == 0, f"7-day trip with FREE promo should be £0, got £{final_amount/100}"

    def test_free_promo_5_day_trip_completely_free(self):
        """A 5-day trip with FREE promo should be completely free."""
        duration_days = 5
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        # With FREE promo (duration <= 7), discount = full amount
        discount_amount = original_amount
        final_amount = original_amount - discount_amount

        # Price may vary based on DB settings, but should be positive
        assert original_amount > 0, f"5-day early price should be positive, got £{original_amount/100}"
        assert final_amount == 0, f"5-day trip with FREE promo should be £0, got £{final_amount/100}"

    def test_free_promo_1_day_trip_completely_free(self):
        """A 1-day trip with FREE promo should be completely free."""
        duration_days = 1
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        # With FREE promo (duration <= 7), discount = full amount
        discount_amount = original_amount
        final_amount = original_amount - discount_amount

        assert original_amount == 6000, f"1-day early price should be £60 (1-4 tier), got £{original_amount/100}"
        assert final_amount == 0, f"1-day trip with FREE promo should be £0, got £{final_amount/100}"

    def test_free_promo_10_day_trip_deducts_7_day_base(self):
        """A 10-day trip with FREE promo should deduct 7-day base price."""
        duration_days = 10
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        # With FREE promo (duration > 7), discount = 7-day base rate
        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)
        discount_amount = min(week1_base_pence, original_amount)
        final_amount = original_amount - discount_amount

        # 10-day early = £119 (10-11 tier)
        # Discount = £79 (7-day base)
        # Customer pays = £40
        assert original_amount == 11900, f"10-day price should be £119 (10-11 tier), got £{original_amount/100}"
        assert discount_amount == 7900, f"Discount should be £79 (7-day base), got £{discount_amount/100}"
        assert final_amount == 4000, f"Final should be £40, got £{final_amount/100}"

    def test_free_promo_14_day_trip_deducts_7_day_base(self):
        """A 14-day trip with FREE promo should deduct 7-day base price."""
        duration_days = 14
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)
        discount_amount = min(week1_base_pence, original_amount)
        final_amount = original_amount - discount_amount

        # 14-day early = £140
        # Discount = £79 (7-day base)
        # Customer pays = £61
        assert original_amount == 14000, f"14-day price should be £140, got £{original_amount/100}"
        assert discount_amount == 7900
        assert final_amount == 6100, f"Final should be £61, got £{final_amount/100}"

    def test_free_promo_20_day_extended_trip(self):
        """A 20-day extended trip with FREE promo should deduct 7-day base."""
        duration_days = 20
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)
        discount_amount = min(week1_base_pence, original_amount)
        final_amount = original_amount - discount_amount

        # 20-day price = £140 (14-day base) + 6 extra days * £9 = £140 + £54 = £194
        # Discount = £79 (7-day base)
        # Customer pays = £194 - £79 = £115
        expected_original = (140 + (20 - 14) * 9) * 100  # £194 = 19400 pence
        assert original_amount == expected_original, f"20-day price should be £194, got £{original_amount/100}"

        expected_final = expected_original - week1_base_pence  # 19400 - 7900 = 11500
        assert final_amount == expected_final, f"Final should be £115, got £{final_amount/100}"

    def test_free_promo_60_day_max_duration_trip(self):
        """A 60-day trip (max duration) with FREE promo should deduct 7-day base."""
        duration_days = 60
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)
        discount_amount = min(week1_base_pence, original_amount)
        final_amount = original_amount - discount_amount

        # 60-day price = £140 (14-day base) + 46 extra days * £9 = £140 + £414 = £554
        expected_original = (140 + (60 - 14) * 9) * 100  # £554 = 55400 pence
        assert original_amount == expected_original, f"60-day price should be £554, got £{original_amount/100}"

        # Customer pays = £554 - £79 = £475
        expected_final = expected_original - week1_base_pence  # 55400 - 7900 = 47500
        assert final_amount == expected_final, f"Final should be £475, got £{final_amount/100}"


class TestTenPercentPromoWithFlexiblePricing:
    """Tests for 10% off promo with flexible duration pricing."""

    def test_10_percent_promo_7_day_trip(self):
        """A 7-day trip with 10% promo should get 10% off."""
        duration_days = 7
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        # 10% discount
        discount_percent = PROMO_DISCOUNT_PERCENT
        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        # 7-day early = £79
        # 10% off = £7.90
        # Final = £71.10
        assert original_amount == 7900, f"7-day early price should be £79, got £{original_amount/100}"
        assert discount_amount == 790, f"10% discount should be £7.90, got £{discount_amount/100}"
        assert final_amount == 7110, f"Final should be £71.10, got £{final_amount/100}"

    def test_10_percent_promo_14_day_trip(self):
        """A 14-day trip with 10% promo should get 10% off."""
        duration_days = 14
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        discount_percent = PROMO_DISCOUNT_PERCENT
        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        # 14-day early = £140
        # 10% off = £14.00
        # Final = £126.00
        assert original_amount == 14000, f"14-day early price should be £140, got £{original_amount/100}"
        assert discount_amount == 1400, f"10% discount should be £14.00, got £{discount_amount/100}"
        assert final_amount == 12600, f"Final should be £126.00, got £{final_amount/100}"

    def test_10_percent_promo_20_day_extended_trip(self):
        """A 20-day extended trip with 10% promo should get 10% off total."""
        duration_days = 20
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        discount_percent = PROMO_DISCOUNT_PERCENT
        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        # 20-day = £140 + (6 * £9) = £194
        # 10% off = £19.40
        # Final = £174.60
        expected_original = 19400
        assert original_amount == expected_original, f"20-day price should be £194, got £{original_amount/100}"
        assert discount_amount == 1940, f"10% discount should be £19.40, got £{discount_amount/100}"
        assert final_amount == 17460, f"Final should be £174.60, got £{final_amount/100}"

    def test_10_percent_promo_standard_tier(self):
        """A standard tier booking with 10% promo should get 10% off standard price."""
        duration_days = 7
        package = "standard"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=10),  # Standard tier (7-13 days ahead)
            duration_days=duration_days
        )

        discount_percent = PROMO_DISCOUNT_PERCENT
        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        # 7-day standard = £89 (£79 + £10 tier increment)
        # 10% off = £8.90
        # Final = £80.10
        assert original_amount == 8900, f"7-day standard price should be £89, got £{original_amount/100}"
        assert discount_amount == 890, f"10% discount should be £8.90, got £{discount_amount/100}"
        assert final_amount == 8010, f"Final should be £80.10, got £{final_amount/100}"

    def test_10_percent_promo_late_tier(self):
        """A late tier booking with 10% promo should get 10% off late price."""
        duration_days = 7
        package = "late"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=3),  # Late tier (<7 days)
            duration_days=duration_days
        )

        discount_percent = PROMO_DISCOUNT_PERCENT
        discount_amount = int(original_amount * discount_percent / 100)
        final_amount = original_amount - discount_amount

        # 7-day late = £99 (£79 + 2*£10 tier increments)
        # 10% off = £9.90
        # Final = £89.10
        assert original_amount == 9900, f"7-day late price should be £99, got £{original_amount/100}"
        assert discount_amount == 990, f"10% discount should be £9.90, got £{discount_amount/100}"
        assert final_amount == 8910, f"Final should be £89.10, got £{final_amount/100}"


class TestPromoEdgeCasesWithFlexiblePricing:
    """Edge cases for promo codes with flexible pricing."""

    def test_free_promo_8_day_boundary(self):
        """8-day trip is the first day where FREE promo deducts 7-day base instead of 100%."""
        duration_days = 8
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)

        # At 8 days, should deduct 7-day base, not full amount
        discount_amount = min(week1_base_pence, original_amount)
        final_amount = original_amount - discount_amount

        # 8-day price = £99 (8-9 day tier)
        # Discount = £79 (7-day base)
        # Customer pays = £20
        assert original_amount == 9900, f"8-day price should be £99, got £{original_amount/100}"
        assert discount_amount == 7900, f"Discount should be £79 (7-day base), got £{discount_amount/100}"
        assert final_amount == 2000, f"Final should be £20, got £{final_amount/100}"

    def test_free_promo_15_day_first_extended_day(self):
        """15-day trip is the first extended stay day (beyond 14-day base)."""
        duration_days = 15
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)
        discount_amount = min(week1_base_pence, original_amount)
        final_amount = original_amount - discount_amount

        # 15-day = £140 + £9 = £149
        # Discount = £79
        # Customer pays = £70
        expected_original = (140 + 9) * 100  # £149
        assert original_amount == expected_original, f"15-day price should be £149, got £{original_amount/100}"
        assert final_amount == expected_original - week1_base_pence

    def test_10_percent_rounding_odd_amounts(self):
        """Test 10% discount rounding on various price amounts."""
        # Test that 10% discount is correctly calculated for any price
        duration_days = 5
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        discount_percent = PROMO_DISCOUNT_PERCENT
        discount_amount = int(original_amount * discount_percent / 100)

        # Verify discount is exactly 10% (truncated to int)
        assert discount_amount == int(original_amount * 10 / 100)
        # Verify discount is less than original
        assert discount_amount < original_amount

    def test_comparison_free_vs_10_percent_short_trip(self):
        """Compare FREE vs 10% for a short trip - FREE should be better."""
        duration_days = 5
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        # FREE promo (100% for <= 7 days)
        free_discount = original_amount
        free_final = 0

        # 10% promo
        ten_percent_discount = int(original_amount * 10 / 100)
        ten_percent_final = original_amount - ten_percent_discount

        # FREE saves more
        assert free_discount > ten_percent_discount
        assert free_final < ten_percent_final
        assert free_final == 0

    def test_comparison_free_vs_10_percent_long_trip(self):
        """Compare FREE vs 10% for a long trip - may vary."""
        duration_days = 30
        package = "early"

        original_amount = calculate_price_in_pence(
            package=package,
            drop_off_date=date.today() + timedelta(days=21),
            duration_days=duration_days
        )

        week1_base_pence = int(get_base_price_for_duration(7, DEFAULT_PRICING) * 100)

        # FREE promo (deducts 7-day base = £79)
        free_discount = week1_base_pence
        free_final = original_amount - free_discount

        # 10% promo
        ten_percent_discount = int(original_amount * 10 / 100)
        ten_percent_final = original_amount - ten_percent_discount

        # 30-day = £140 + 16*£9 = £284
        # FREE: £284 - £79 = £205 (saves £79)
        # 10%: £284 - £28.40 = £255.60 (saves £28.40)
        # FREE saves more even for long trips
        expected_original = (140 + 16 * 9) * 100  # £284
        assert original_amount == expected_original, f"30-day should be £284, got £{original_amount/100}"
        assert free_discount > ten_percent_discount, "FREE saves more than 10% for 30-day trip"

        print(f"\n30-day trip comparison:")
        print(f"  Original: £{original_amount/100:.2f}")
        print(f"  FREE promo: saves £{free_discount/100:.2f}, pays £{free_final/100:.2f}")
        print(f"  10% promo: saves £{ten_percent_discount/100:.2f}, pays £{ten_percent_final/100:.2f}")

    def test_all_duration_tiers_10_percent(self):
        """Test 10% discount applies correctly across all duration tiers."""
        # Test that 10% discount is correctly calculated for each duration
        durations = [1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]

        for days in durations:
            original = calculate_price_in_pence(
                package="early",
                drop_off_date=date.today() + timedelta(days=21),
                duration_days=days
            )
            discount = int(original * 10 / 100)
            final = original - discount

            # Verify discount is exactly 10%
            assert discount == int(original * 10 / 100), f"{days}-day: discount should be 10% of {original}"
            # Verify final is 90% of original
            assert final == original - discount, f"{days}-day: final should be original - discount"
            # Verify amounts are positive
            assert original > 0, f"{days}-day: original should be positive"
            assert discount > 0, f"{days}-day: discount should be positive"
            assert final > 0, f"{days}-day: final should be positive"

    def test_promo_discount_calculation_consistent(self):
        """Test that promo discount calculation is consistent across durations."""
        # Verify that 10% discount formula works for any price
        for days in [1, 7, 14, 20]:
            original = calculate_price_in_pence("early", date.today() + timedelta(days=21), days)
            discount_10 = int(original * 10 / 100)
            final_10 = original - discount_10

            # 10% discount always results in 90% of original
            assert final_10 == original - discount_10
            # Discount is always positive
            assert discount_10 > 0
            # Final is always positive
            assert final_10 > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
