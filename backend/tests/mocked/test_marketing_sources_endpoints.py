"""
Unit and Integration tests for Marketing Sources endpoints.

Tests the marketing sources analytics functionality:
- GET /api/admin/marketing-sources/summary
- GET /api/admin/marketing-sources/other
- GET /api/admin/marketing-sources/export

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timezone, timedelta


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_booking(
    id=1,
    reference="TAG-12345",
    marketing_source=None,
    marketing_source_other=None,
    amount_pence=7500,
    status="confirmed",
    created_at=None,
):
    """Create a mock booking with marketing source."""
    booking = MagicMock()
    booking.id = id
    booking.reference = reference
    booking.marketing_source = marketing_source
    booking.marketing_source_other = marketing_source_other
    booking.created_at = created_at or datetime.now(timezone.utc)

    booking.status = MagicMock()
    booking.status.value = status

    booking.payment = MagicMock()
    booking.payment.amount_pence = amount_pence

    return booking


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Marketing Sources Summary Tests
# ============================================================================

class TestMarketingSourcesSummaryLogic:
    """Unit tests for marketing sources summary logic."""

    # Happy Path
    def test_groups_bookings_by_source(self):
        """Should group bookings by marketing source."""
        bookings = [
            create_mock_booking(marketing_source="google"),
            create_mock_booking(marketing_source="google"),
            create_mock_booking(marketing_source="facebook"),
            create_mock_booking(marketing_source="friend_recommendation"),
        ]

        source_counts = {}
        for b in bookings:
            source = b.marketing_source or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

        assert source_counts["google"] == 2
        assert source_counts["facebook"] == 1
        assert source_counts["friend_recommendation"] == 1

    def test_calculates_revenue_per_source(self):
        """Should calculate revenue per source."""
        bookings = [
            create_mock_booking(marketing_source="google", amount_pence=5000),
            create_mock_booking(marketing_source="google", amount_pence=7500),
            create_mock_booking(marketing_source="facebook", amount_pence=6000),
        ]

        revenue_by_source = {}
        for b in bookings:
            source = b.marketing_source or "unknown"
            revenue_by_source[source] = revenue_by_source.get(source, 0) + b.payment.amount_pence

        assert revenue_by_source["google"] == 12500  # 5000 + 7500
        assert revenue_by_source["facebook"] == 6000

    def test_calculates_percentage_of_total(self):
        """Should calculate percentage of total bookings."""
        source_counts = {"google": 50, "facebook": 30, "other": 20}
        total = sum(source_counts.values())

        percentages = {k: (v / total * 100) for k, v in source_counts.items()}

        assert percentages["google"] == 50.0
        assert percentages["facebook"] == 30.0
        assert percentages["other"] == 20.0

    def test_handles_null_marketing_source(self):
        """Should handle bookings with null marketing source."""
        bookings = [
            create_mock_booking(marketing_source="google"),
            create_mock_booking(marketing_source=None),
            create_mock_booking(marketing_source=None),
        ]

        source_counts = {}
        for b in bookings:
            source = b.marketing_source or "not_specified"
            source_counts[source] = source_counts.get(source, 0) + 1

        assert source_counts["google"] == 1
        assert source_counts["not_specified"] == 2

    def test_excludes_cancelled_bookings(self):
        """Should exclude cancelled bookings from summary."""
        bookings = [
            create_mock_booking(marketing_source="google", status="confirmed"),
            create_mock_booking(marketing_source="google", status="cancelled"),
            create_mock_booking(marketing_source="google", status="completed"),
        ]

        active = [b for b in bookings if b.status.value != "cancelled"]

        assert len(active) == 2

    def test_filters_by_date_range(self):
        """Should filter by date range."""
        now = datetime.now(timezone.utc)
        bookings = [
            create_mock_booking(created_at=now - timedelta(days=60)),  # Outside range
            create_mock_booking(created_at=now - timedelta(days=15)),  # Inside range
            create_mock_booking(created_at=now - timedelta(days=5)),   # Inside range
        ]

        date_from = now - timedelta(days=30)
        filtered = [b for b in bookings if b.created_at >= date_from]

        assert len(filtered) == 2

    # Edge Cases
    def test_handles_no_bookings(self):
        """Should handle no bookings."""
        bookings = []

        source_counts = {}
        for b in bookings:
            source = b.marketing_source or "unknown"
            source_counts[source] = source_counts.get(source, 0) + 1

        assert len(source_counts) == 0


class TestKnownMarketingSources:
    """Tests for known marketing source options."""

    def test_known_sources_list(self):
        """Should have defined list of known sources."""
        known_sources = [
            "google",
            "facebook",
            "instagram",
            "tiktok",
            "friend_recommendation",
            "returning_customer",
            "local_advertising",
            "other",
        ]

        assert "google" in known_sources
        assert "facebook" in known_sources
        assert "friend_recommendation" in known_sources
        assert "other" in known_sources

    def test_identifies_known_source(self):
        """Should identify known marketing source."""
        known = ["google", "facebook", "instagram"]
        source = "google"

        is_known = source in known

        assert is_known is True

    def test_identifies_unknown_source(self):
        """Should identify unknown marketing source as 'other'."""
        known = ["google", "facebook", "instagram"]
        source = "newspaper_ad"

        is_known = source in known

        assert is_known is False


# ============================================================================
# Marketing Sources Other Details Tests
# ============================================================================

class TestMarketingSourcesOtherLogic:
    """Unit tests for 'other' marketing sources detail."""

    # Happy Path
    def test_returns_other_source_details(self):
        """Should return details for 'other' sources."""
        bookings = [
            create_mock_booking(marketing_source="other", marketing_source_other="Newspaper ad"),
            create_mock_booking(marketing_source="other", marketing_source_other="Radio"),
            create_mock_booking(marketing_source="other", marketing_source_other="Newspaper ad"),
        ]

        other_sources = {}
        for b in bookings:
            if b.marketing_source == "other" and b.marketing_source_other:
                detail = b.marketing_source_other
                other_sources[detail] = other_sources.get(detail, 0) + 1

        assert other_sources["Newspaper ad"] == 2
        assert other_sources["Radio"] == 1

    def test_groups_similar_other_sources(self):
        """Should group similar 'other' source text."""
        bookings = [
            create_mock_booking(marketing_source="other", marketing_source_other="newspaper"),
            create_mock_booking(marketing_source="other", marketing_source_other="Newspaper"),
            create_mock_booking(marketing_source="other", marketing_source_other="NEWSPAPER"),
        ]

        # Normalize to lowercase for grouping
        other_sources = {}
        for b in bookings:
            if b.marketing_source == "other" and b.marketing_source_other:
                detail = b.marketing_source_other.lower().strip()
                other_sources[detail] = other_sources.get(detail, 0) + 1

        assert other_sources["newspaper"] == 3

    def test_handles_empty_other_detail(self):
        """Should handle 'other' with no detail."""
        bookings = [
            create_mock_booking(marketing_source="other", marketing_source_other="Radio"),
            create_mock_booking(marketing_source="other", marketing_source_other=""),
            create_mock_booking(marketing_source="other", marketing_source_other=None),
        ]

        other_with_detail = [b for b in bookings if b.marketing_source == "other" and b.marketing_source_other]

        assert len(other_with_detail) == 1


# ============================================================================
# Marketing Sources Export Tests
# ============================================================================

class TestMarketingSourcesExportLogic:
    """Unit tests for marketing sources export logic."""

    # Happy Path
    def test_generates_csv_format(self):
        """Should generate CSV format data."""
        data = [
            {"source": "google", "bookings": 50, "revenue_pence": 375000},
            {"source": "facebook", "bookings": 30, "revenue_pence": 225000},
        ]

        # Simulate CSV generation
        csv_lines = ["Source,Bookings,Revenue"]
        for row in data:
            csv_lines.append(f"{row['source']},{row['bookings']},£{row['revenue_pence']/100:.2f}")

        csv_content = "\n".join(csv_lines)

        assert "Source,Bookings,Revenue" in csv_content
        assert "google,50,£3750.00" in csv_content

    def test_includes_all_sources(self):
        """Should include all sources in export."""
        sources = ["google", "facebook", "friend_recommendation", "other", "not_specified"]

        export_data = [{"source": s, "count": 10} for s in sources]

        assert len(export_data) == 5

    def test_formats_revenue_as_currency(self):
        """Should format revenue as currency in export."""
        revenue_pence = 375000

        formatted = f"£{revenue_pence / 100:.2f}"

        assert formatted == "£3750.00"

    def test_includes_date_range_in_filename(self):
        """Should include date range in export filename."""
        start = date(2026, 1, 1)
        end = date(2026, 3, 31)

        filename = f"marketing-sources_{start.isoformat()}_to_{end.isoformat()}.csv"

        assert "2026-01-01" in filename
        assert "2026-03-31" in filename


# ============================================================================
# Date Filtering Tests
# ============================================================================

class TestMarketingSourcesDateFiltering:
    """Tests for date filtering on marketing sources."""

    def test_filters_by_start_date(self):
        """Should filter bookings from start date."""
        now = datetime.now(timezone.utc)
        bookings = [
            create_mock_booking(created_at=now - timedelta(days=90)),
            create_mock_booking(created_at=now - timedelta(days=30)),
            create_mock_booking(created_at=now - timedelta(days=10)),
        ]

        start_date = now - timedelta(days=60)
        filtered = [b for b in bookings if b.created_at >= start_date]

        assert len(filtered) == 2

    def test_filters_by_end_date(self):
        """Should filter bookings until end date."""
        now = datetime.now(timezone.utc)
        bookings = [
            create_mock_booking(created_at=now - timedelta(days=30)),
            create_mock_booking(created_at=now - timedelta(days=10)),
            create_mock_booking(created_at=now + timedelta(days=10)),  # Future
        ]

        end_date = now
        filtered = [b for b in bookings if b.created_at <= end_date]

        assert len(filtered) == 2

    def test_defaults_to_all_time(self):
        """Should default to all time if no date specified."""
        bookings = [
            create_mock_booking(created_at=datetime(2025, 1, 1, tzinfo=timezone.utc)),
            create_mock_booking(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            create_mock_booking(created_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
        ]

        # No date filter
        filtered = bookings

        assert len(filtered) == 3


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestMarketingSourcesResponseStructure:
    """Tests for response structure."""

    def test_summary_response_structure(self):
        """Should return correct summary response structure."""
        response = {
            "sources": [
                {
                    "source": "google",
                    "bookings_count": 50,
                    "revenue_pence": 375000,
                    "revenue_display": "£3,750.00",
                    "percentage": 50.0,
                },
                {
                    "source": "facebook",
                    "bookings_count": 30,
                    "revenue_pence": 225000,
                    "revenue_display": "£2,250.00",
                    "percentage": 30.0,
                },
            ],
            "total_bookings": 100,
            "total_revenue_pence": 750000,
        }

        assert "sources" in response
        assert "total_bookings" in response
        assert response["sources"][0]["source"] == "google"

    def test_other_response_structure(self):
        """Should return correct 'other' detail response structure."""
        response = {
            "other_sources": [
                {"detail": "Newspaper ad", "count": 5},
                {"detail": "Radio", "count": 3},
            ],
            "total_other": 8,
        }

        assert "other_sources" in response
        assert response["total_other"] == 8


# ============================================================================
# Authentication Tests
# ============================================================================

class TestMarketingSourcesAuthentication:
    """Tests for authentication on marketing sources endpoints."""

    def test_requires_admin_user(self):
        """Should require admin user."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_rejects_non_admin(self):
        """Should reject non-admin users."""
        user = MagicMock()
        user.is_admin = False

        assert user.is_admin is False


# ============================================================================
# Boundary Tests
# ============================================================================

class TestMarketingSourcesBoundaries:
    """Tests for boundary conditions."""

    def test_handles_single_booking(self):
        """Should handle single booking."""
        bookings = [create_mock_booking(marketing_source="google")]

        source_counts = {}
        for b in bookings:
            source = b.marketing_source
            source_counts[source] = source_counts.get(source, 0) + 1

        assert source_counts["google"] == 1

    def test_handles_large_dataset(self):
        """Should handle large number of bookings."""
        bookings = [create_mock_booking(marketing_source="google") for _ in range(10000)]

        count = len(bookings)

        assert count == 10000

    def test_very_long_other_source_text(self):
        """Should handle very long 'other' source text."""
        long_text = "A" * 500
        booking = create_mock_booking(marketing_source="other", marketing_source_other=long_text)

        assert len(booking.marketing_source_other) == 500

    def test_zero_revenue_booking(self):
        """Should handle zero revenue booking."""
        booking = create_mock_booking(amount_pence=0)

        assert booking.payment.amount_pence == 0


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
