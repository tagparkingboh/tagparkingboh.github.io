"""
Tests for Google Ads bid recommendation feature.

Covers:
- Day-of-week recommendation logic
- Conversion rate calculations
- Recommendation categorization (increase/maintain/reduce)
- Priority assignment (high/medium/low)
- Peak hours identification
- Edge cases (no data, single day, zero searches)

All tests use mocked data - no real database connections.
"""
import pytest
from datetime import datetime
from collections import defaultdict


# ============================================================================
# BID RECOMMENDATION LOGIC (Mirror of main.py implementation)
# ============================================================================

def calculate_bid_recommendations(
    booking_hours_by_day: dict,
    search_hours_by_day: dict,
    total_searches: int,
    total_successful: int
) -> tuple[list, float]:
    """
    Calculate bid recommendations for each day of week.

    Returns:
        tuple: (bid_recommendations list, overall_conversion_rate)
    """
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    bid_recommendations = []

    # Calculate overall conversion rate
    overall_conversion = round((total_successful / total_searches * 100), 1) if total_searches > 0 else 0
    avg_conversion = overall_conversion

    for day in day_names:
        day_searches = sum(search_hours_by_day.get(day, {}).values())
        day_bookings = sum(booking_hours_by_day.get(day, {}).values())

        # Calculate conversion rate for this day
        conversion_rate = round((day_bookings / day_searches * 100), 1) if day_searches > 0 else 0

        # Calculate this day's share of total activity
        search_share = round((day_searches / total_searches * 100), 1) if total_searches > 0 else 0
        booking_share = round((day_bookings / total_successful * 100), 1) if total_successful > 0 else 0

        # Identify peak hours for this day (top 3 hours by searches)
        day_search_hours = search_hours_by_day.get(day, {})
        sorted_hours = sorted(day_search_hours.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, c in sorted_hours[:3] if c > 0]

        # Identify peak booking hours for this day (top 3 hours by bookings)
        day_booking_hours = booking_hours_by_day.get(day, {})
        sorted_booking_hours = sorted(day_booking_hours.items(), key=lambda x: x[1], reverse=True)
        peak_booking_hours = [h for h, c in sorted_booking_hours[:3] if c > 0]

        # Calculate hourly conversion rates
        hourly_conversions = []
        for hour in range(24):
            h_searches = day_search_hours.get(hour, 0)
            h_bookings = day_booking_hours.get(hour, 0)
            if h_searches > 0:
                h_conv = round((h_bookings / h_searches * 100), 1)
                hourly_conversions.append({
                    "hour": hour,
                    "label": f"{hour:02d}:00",
                    "searches": h_searches,
                    "bookings": h_bookings,
                    "conversion_rate": h_conv
                })

        # Sort by conversion rate
        high_converting_hours = sorted(
            [h for h in hourly_conversions if h["searches"] >= 3],
            key=lambda x: x["conversion_rate"],
            reverse=True
        )[:3]

        low_converting_hours = sorted(
            [h for h in hourly_conversions if h["searches"] >= 3 and h["conversion_rate"] < 50],
            key=lambda x: x["conversion_rate"]
        )[:3]

        # Generate bid recommendation
        avg_daily_search_share = 100 / 7  # ~14.3%

        if search_share >= avg_daily_search_share * 1.2:  # 20% above average
            if conversion_rate >= avg_conversion:
                recommendation = "increase"
                reason = f"High search volume ({search_share}% of weekly) with strong conversion ({conversion_rate}%)"
                priority = "high"
            else:
                recommendation = "maintain"
                reason = f"High search volume ({search_share}% of weekly) but below-average conversion ({conversion_rate}% vs {avg_conversion}% avg)"
                priority = "medium"
        elif search_share <= avg_daily_search_share * 0.8:  # 20% below average
            if conversion_rate >= avg_conversion * 1.2:  # 20% above average conversion
                recommendation = "increase"
                reason = f"Lower volume but excellent conversion ({conversion_rate}%) - untapped opportunity"
                priority = "medium"
            else:
                recommendation = "reduce"
                reason = f"Low search volume ({search_share}% of weekly) with weak conversion ({conversion_rate}%)"
                priority = "low"
        else:
            if conversion_rate >= avg_conversion * 1.2:
                recommendation = "increase"
                reason = f"Average volume with above-average conversion ({conversion_rate}%)"
                priority = "medium"
            elif conversion_rate <= avg_conversion * 0.8:
                recommendation = "reduce"
                reason = f"Average volume but below-average conversion ({conversion_rate}% vs {avg_conversion}% avg)"
                priority = "medium"
            else:
                recommendation = "maintain"
                reason = f"Average performance ({conversion_rate}% conversion, {search_share}% of searches)"
                priority = "low"

        # Format peak hours for display
        peak_hours_formatted = [f"{h:02d}:00-{(h+1) % 24:02d}:00" for h in peak_hours] if peak_hours else []
        peak_booking_hours_formatted = [f"{h:02d}:00-{(h+1) % 24:02d}:00" for h in peak_booking_hours] if peak_booking_hours else []

        bid_recommendations.append({
            "day": day,
            "searches": day_searches,
            "bookings": day_bookings,
            "conversion_rate": conversion_rate,
            "search_share": search_share,
            "booking_share": booking_share,
            "recommendation": recommendation,
            "reason": reason,
            "priority": priority,
            "peak_search_hours": peak_hours_formatted,
            "peak_booking_hours": peak_booking_hours_formatted,
            "high_converting_hours": high_converting_hours,
            "low_converting_hours": low_converting_hours,
        })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    bid_recommendations_sorted = sorted(bid_recommendations, key=lambda x: priority_order[x["priority"]])

    return bid_recommendations_sorted, overall_conversion


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_hourly_data(hours_with_counts: dict) -> dict:
    """Create a full 24-hour dict with given counts, 0 for others."""
    data = {hour: 0 for hour in range(24)}
    data.update(hours_with_counts)
    return data


def create_week_data(daily_hourly_data: dict) -> dict:
    """Create a week of data with given day -> hourly data."""
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    result = {}
    for day in day_names:
        result[day] = daily_hourly_data.get(day, create_hourly_data({}))
    return result


# ============================================================================
# MOCKED UNIT TESTS - Recommendation Logic
# ============================================================================

class TestRecommendationLogic:
    """Unit tests for bid recommendation calculation logic."""

    def test_high_volume_high_conversion_increase(self):
        """Happy path: High search volume + high conversion = INCREASE recommendation."""
        # Monday has 30% of searches (above 14.3% avg) with 25% conversion (above avg)
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 20, 11: 15, 12: 10, 14: 15, 15: 10}),  # 70 searches
            "Tuesday": create_hourly_data({10: 5, 11: 5}),  # 10 searches
            "Wednesday": create_hourly_data({10: 5}),
            "Thursday": create_hourly_data({10: 5}),
            "Friday": create_hourly_data({10: 5}),
            "Saturday": create_hourly_data({10: 5}),
            "Sunday": create_hourly_data({10: 5}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 5, 11: 4, 12: 3, 14: 4, 15: 2}),  # 18 bookings = 25.7% conversion
            "Tuesday": create_hourly_data({10: 1}),
            "Wednesday": create_hourly_data({10: 1}),
            "Thursday": create_hourly_data({10: 1}),
            "Friday": create_hourly_data({10: 1}),
            "Saturday": create_hourly_data({10: 1}),
            "Sunday": create_hourly_data({10: 1}),
        })

        total_searches = 100
        total_bookings = 24

        recommendations, overall_conv = calculate_bid_recommendations(
            booking_data, search_data, total_searches, total_bookings
        )

        # Find Monday's recommendation
        monday_rec = next(r for r in recommendations if r["day"] == "Monday")

        assert monday_rec["recommendation"] == "increase"
        assert monday_rec["priority"] == "high"
        assert "High search volume" in monday_rec["reason"]
        assert monday_rec["searches"] == 70
        assert monday_rec["bookings"] == 18

    def test_high_volume_low_conversion_maintain(self):
        """High search volume + low conversion = MAINTAIN recommendation."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 50, 11: 30}),  # 80 searches (high volume)
            "Tuesday": create_hourly_data({10: 5}),
            "Wednesday": create_hourly_data({10: 5}),
            "Thursday": create_hourly_data({10: 5}),
            "Friday": create_hourly_data({10: 5}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 2, 11: 1}),  # 3 bookings = 3.75% conversion (very low)
            "Tuesday": create_hourly_data({10: 2}),
            "Wednesday": create_hourly_data({10: 2}),
            "Thursday": create_hourly_data({10: 2}),
            "Friday": create_hourly_data({10: 2}),
        })

        total_searches = 100
        total_bookings = 11

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, total_searches, total_bookings
        )

        monday_rec = next(r for r in recommendations if r["day"] == "Monday")

        assert monday_rec["recommendation"] == "maintain"
        assert monday_rec["priority"] == "medium"
        assert "below-average conversion" in monday_rec["reason"]

    def test_low_volume_high_conversion_increase(self):
        """Low search volume + excellent conversion = INCREASE (untapped opportunity)."""
        # Sunday has only 5% of searches but 50% conversion (well above 20% average)
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 20}),
            "Tuesday": create_hourly_data({10: 20}),
            "Wednesday": create_hourly_data({10: 20}),
            "Thursday": create_hourly_data({10: 20}),
            "Friday": create_hourly_data({10: 20}),
            "Saturday": create_hourly_data({10: 20}),
            "Sunday": create_hourly_data({10: 5}),  # Only 5 searches (low volume)
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 3}),  # 15% conversion
            "Tuesday": create_hourly_data({10: 3}),
            "Wednesday": create_hourly_data({10: 3}),
            "Thursday": create_hourly_data({10: 3}),
            "Friday": create_hourly_data({10: 3}),
            "Saturday": create_hourly_data({10: 3}),
            "Sunday": create_hourly_data({10: 3}),  # 60% conversion (high!)
        })

        total_searches = 125
        total_bookings = 21

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, total_searches, total_bookings
        )

        sunday_rec = next(r for r in recommendations if r["day"] == "Sunday")

        assert sunday_rec["recommendation"] == "increase"
        assert sunday_rec["priority"] == "medium"
        assert "untapped opportunity" in sunday_rec["reason"]

    def test_low_volume_low_conversion_reduce(self):
        """Low search volume + weak conversion = REDUCE recommendation."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 30}),
            "Tuesday": create_hourly_data({10: 30}),
            "Wednesday": create_hourly_data({10: 5}),  # Low volume
            "Thursday": create_hourly_data({10: 30}),
            "Friday": create_hourly_data({10: 30}),
            "Saturday": create_hourly_data({10: 30}),
            "Sunday": create_hourly_data({10: 30}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 6}),  # 20% conversion
            "Tuesday": create_hourly_data({10: 6}),
            "Wednesday": create_hourly_data({10: 0}),  # 0% conversion (weak)
            "Thursday": create_hourly_data({10: 6}),
            "Friday": create_hourly_data({10: 6}),
            "Saturday": create_hourly_data({10: 6}),
            "Sunday": create_hourly_data({10: 6}),
        })

        total_searches = 185
        total_bookings = 36

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, total_searches, total_bookings
        )

        wednesday_rec = next(r for r in recommendations if r["day"] == "Wednesday")

        assert wednesday_rec["recommendation"] == "reduce"
        assert wednesday_rec["priority"] == "low"
        assert "weak conversion" in wednesday_rec["reason"]

    def test_average_volume_above_avg_conversion_increase(self):
        """Average volume + above-average conversion = INCREASE."""
        # Even distribution with Saturday having slightly higher conversion
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 15}),
            "Tuesday": create_hourly_data({10: 15}),
            "Wednesday": create_hourly_data({10: 15}),
            "Thursday": create_hourly_data({10: 15}),
            "Friday": create_hourly_data({10: 15}),
            "Saturday": create_hourly_data({10: 15}),  # 14.3% = average
            "Sunday": create_hourly_data({10: 15}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 2}),  # 13.3% conversion
            "Tuesday": create_hourly_data({10: 2}),
            "Wednesday": create_hourly_data({10: 2}),
            "Thursday": create_hourly_data({10: 2}),
            "Friday": create_hourly_data({10: 2}),
            "Saturday": create_hourly_data({10: 5}),  # 33.3% conversion (high!)
            "Sunday": create_hourly_data({10: 2}),
        })

        total_searches = 105
        total_bookings = 17

        recommendations, overall_conv = calculate_bid_recommendations(
            booking_data, search_data, total_searches, total_bookings
        )

        saturday_rec = next(r for r in recommendations if r["day"] == "Saturday")

        # Saturday should be "increase" because it has above-average conversion
        assert saturday_rec["recommendation"] == "increase"
        assert saturday_rec["priority"] == "medium"

    def test_average_volume_below_avg_conversion_reduce(self):
        """Average volume + below-average conversion = REDUCE."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 15}),
            "Tuesday": create_hourly_data({10: 15}),
            "Wednesday": create_hourly_data({10: 15}),  # Average volume
            "Thursday": create_hourly_data({10: 15}),
            "Friday": create_hourly_data({10: 15}),
            "Saturday": create_hourly_data({10: 15}),
            "Sunday": create_hourly_data({10: 15}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 4}),  # 26.7% conversion
            "Tuesday": create_hourly_data({10: 4}),
            "Wednesday": create_hourly_data({10: 1}),  # 6.7% conversion (low!)
            "Thursday": create_hourly_data({10: 4}),
            "Friday": create_hourly_data({10: 4}),
            "Saturday": create_hourly_data({10: 4}),
            "Sunday": create_hourly_data({10: 4}),
        })

        total_searches = 105
        total_bookings = 25

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, total_searches, total_bookings
        )

        wednesday_rec = next(r for r in recommendations if r["day"] == "Wednesday")

        assert wednesday_rec["recommendation"] == "reduce"
        assert wednesday_rec["priority"] == "medium"


# ============================================================================
# MOCKED UNIT TESTS - Peak Hours Identification
# ============================================================================

class TestPeakHoursIdentification:
    """Unit tests for peak hours identification."""

    def test_peak_search_hours_identified(self):
        """Peak search hours are correctly identified (top 3)."""
        search_data = create_week_data({
            "Monday": create_hourly_data({9: 5, 10: 20, 11: 15, 12: 8, 14: 25, 15: 10}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 2, 14: 3}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 83, 5
        )

        monday_rec = next(r for r in recommendations if r["day"] == "Monday")

        # Top 3 search hours: 14 (25), 10 (20), 11 (15)
        assert "14:00-15:00" in monday_rec["peak_search_hours"]
        assert "10:00-11:00" in monday_rec["peak_search_hours"]
        assert "11:00-12:00" in monday_rec["peak_search_hours"]
        assert len(monday_rec["peak_search_hours"]) == 3

    def test_peak_booking_hours_identified(self):
        """Peak booking hours are correctly identified (top 3)."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 10, 14: 10, 15: 10, 16: 10}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 5, 14: 8, 15: 3, 16: 2}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 40, 18
        )

        monday_rec = next(r for r in recommendations if r["day"] == "Monday")

        # Top 3 booking hours: 14 (8), 10 (5), 15 (3)
        assert "14:00-15:00" in monday_rec["peak_booking_hours"]
        assert "10:00-11:00" in monday_rec["peak_booking_hours"]
        assert "15:00-16:00" in monday_rec["peak_booking_hours"]

    def test_high_converting_hours_identified(self):
        """High converting hours are correctly identified."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 10, 11: 10, 12: 10, 14: 10}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 8, 11: 2, 12: 7, 14: 1}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 40, 18
        )

        monday_rec = next(r for r in recommendations if r["day"] == "Monday")

        # High converting: 10 (80%), 12 (70%), 11 (20%), 14 (10%)
        # Sorted by conversion rate, top 3 with >= 3 searches
        high_conv = monday_rec["high_converting_hours"]

        assert len(high_conv) <= 3
        if len(high_conv) > 0:
            assert high_conv[0]["hour"] == 10  # 80% conversion
            assert high_conv[0]["conversion_rate"] == 80.0


# ============================================================================
# MOCKED UNIT TESTS - Edge Cases
# ============================================================================

class TestEdgeCases:
    """Unit tests for edge cases."""

    def test_no_searches_day(self):
        """Day with no searches gets 0% conversion and reduce recommendation."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 20}),
            "Tuesday": create_hourly_data({}),  # No searches
            "Wednesday": create_hourly_data({10: 20}),
            "Thursday": create_hourly_data({10: 20}),
            "Friday": create_hourly_data({10: 20}),
            "Saturday": create_hourly_data({10: 20}),
            "Sunday": create_hourly_data({10: 20}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 4}),
            "Tuesday": create_hourly_data({}),  # No bookings either
            "Wednesday": create_hourly_data({10: 4}),
            "Thursday": create_hourly_data({10: 4}),
            "Friday": create_hourly_data({10: 4}),
            "Saturday": create_hourly_data({10: 4}),
            "Sunday": create_hourly_data({10: 4}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 120, 24
        )

        tuesday_rec = next(r for r in recommendations if r["day"] == "Tuesday")

        assert tuesday_rec["searches"] == 0
        assert tuesday_rec["bookings"] == 0
        assert tuesday_rec["conversion_rate"] == 0
        assert tuesday_rec["recommendation"] == "reduce"

    def test_zero_total_searches(self):
        """Handle zero total searches gracefully."""
        search_data = create_week_data({})
        booking_data = create_week_data({})

        recommendations, overall_conv = calculate_bid_recommendations(
            booking_data, search_data, 0, 0
        )

        assert overall_conv == 0
        assert len(recommendations) == 7
        for rec in recommendations:
            assert rec["search_share"] == 0
            assert rec["conversion_rate"] == 0

    def test_all_days_same_performance(self):
        """When all days have same performance, all should be maintain."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 10}),
            "Tuesday": create_hourly_data({10: 10}),
            "Wednesday": create_hourly_data({10: 10}),
            "Thursday": create_hourly_data({10: 10}),
            "Friday": create_hourly_data({10: 10}),
            "Saturday": create_hourly_data({10: 10}),
            "Sunday": create_hourly_data({10: 10}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 2}),
            "Tuesday": create_hourly_data({10: 2}),
            "Wednesday": create_hourly_data({10: 2}),
            "Thursday": create_hourly_data({10: 2}),
            "Friday": create_hourly_data({10: 2}),
            "Saturday": create_hourly_data({10: 2}),
            "Sunday": create_hourly_data({10: 2}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 70, 14
        )

        # All should be "maintain" since they're all average
        for rec in recommendations:
            assert rec["recommendation"] == "maintain"
            assert rec["priority"] == "low"

    def test_priority_sorting(self):
        """Recommendations are sorted by priority (high first)."""
        # Create varied performance
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 50}),  # High volume
            "Tuesday": create_hourly_data({10: 5}),   # Low volume
            "Wednesday": create_hourly_data({10: 14}),  # Average
            "Thursday": create_hourly_data({10: 14}),
            "Friday": create_hourly_data({10: 14}),
            "Saturday": create_hourly_data({10: 14}),
            "Sunday": create_hourly_data({10: 14}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 15}),  # 30% conv
            "Tuesday": create_hourly_data({10: 0}),   # 0% conv
            "Wednesday": create_hourly_data({10: 3}),
            "Thursday": create_hourly_data({10: 3}),
            "Friday": create_hourly_data({10: 3}),
            "Saturday": create_hourly_data({10: 3}),
            "Sunday": create_hourly_data({10: 3}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 125, 30
        )

        # Should be sorted: high priority first, then medium, then low
        priorities = [r["priority"] for r in recommendations]

        # Check that priorities are in order
        priority_values = {"high": 0, "medium": 1, "low": 2}
        for i in range(len(priorities) - 1):
            assert priority_values[priorities[i]] <= priority_values[priorities[i + 1]]


# ============================================================================
# MOCKED UNIT TESTS - Output Format
# ============================================================================

class TestOutputFormat:
    """Unit tests for correct output format."""

    def test_all_fields_present(self):
        """All required fields are present in recommendation."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 10}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 2}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 70, 14
        )

        rec = recommendations[0]

        required_fields = [
            "day", "searches", "bookings", "conversion_rate",
            "search_share", "booking_share", "recommendation",
            "reason", "priority", "peak_search_hours",
            "peak_booking_hours", "high_converting_hours", "low_converting_hours"
        ]

        for field in required_fields:
            assert field in rec, f"Missing field: {field}"

    def test_recommendation_values_valid(self):
        """Recommendation values are one of: increase, maintain, reduce."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 10}),
            "Tuesday": create_hourly_data({10: 10}),
            "Wednesday": create_hourly_data({10: 10}),
            "Thursday": create_hourly_data({10: 10}),
            "Friday": create_hourly_data({10: 10}),
            "Saturday": create_hourly_data({10: 10}),
            "Sunday": create_hourly_data({10: 10}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 2}),
            "Tuesday": create_hourly_data({10: 2}),
            "Wednesday": create_hourly_data({10: 2}),
            "Thursday": create_hourly_data({10: 2}),
            "Friday": create_hourly_data({10: 2}),
            "Saturday": create_hourly_data({10: 2}),
            "Sunday": create_hourly_data({10: 2}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 70, 14
        )

        valid_recommendations = {"increase", "maintain", "reduce"}
        valid_priorities = {"high", "medium", "low"}

        for rec in recommendations:
            assert rec["recommendation"] in valid_recommendations
            assert rec["priority"] in valid_priorities

    def test_peak_hours_format(self):
        """Peak hours are formatted as HH:00-HH:00."""
        search_data = create_week_data({
            "Monday": create_hourly_data({9: 5, 23: 10}),  # Include midnight wrap
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({9: 1, 23: 2}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 15, 3
        )

        monday_rec = next(r for r in recommendations if r["day"] == "Monday")

        # Check format: should be "23:00-00:00" for hour 23
        for hour_range in monday_rec["peak_search_hours"]:
            assert "-" in hour_range
            start, end = hour_range.split("-")
            assert len(start) == 5  # "HH:00"
            assert len(end) == 5

    def test_seven_days_returned(self):
        """Always returns exactly 7 days."""
        search_data = create_week_data({
            "Monday": create_hourly_data({10: 5}),
        })
        booking_data = create_week_data({
            "Monday": create_hourly_data({10: 1}),
        })

        recommendations, _ = calculate_bid_recommendations(
            booking_data, search_data, 5, 1
        )

        assert len(recommendations) == 7

        days = {r["day"] for r in recommendations}
        expected_days = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
        assert days == expected_days
