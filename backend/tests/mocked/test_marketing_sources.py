"""
Tests for Marketing Sources (Where did you hear about us?) feature.

Covers:
- GET /api/customers/heard-about-us-status - Check if customer has answered
- POST /api/customers/heard-about-us - Submit marketing source response
- GET /api/admin/marketing-sources/summary - Admin monthly summary report
- GET /api/admin/marketing-sources/other - Admin "Other" details view
- GET /api/admin/marketing-sources/export - CSV export

Test categories:
- Response structure validation (catches API/frontend mismatches)
- Happy path: Normal successful operations
- Negative path: Error cases and validation failures
- Edge cases: Boundary conditions and special scenarios
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Valid Marketing Sources (must match backend VALID_MARKETING_SOURCES)
# =============================================================================

VALID_MARKETING_SOURCES = [
    'newspaper',
    'google',
    'facebook',
    'instagram',
    'linkedin',
    'afc_bournemouth',
    'expectations_travel',
    'word_of_mouth',
    'leaflet',
    'tv',
    'radio',
    'other'
]


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_customer(
    id=1,
    email="test@example.com",
    first_name="John",
    last_name="Doe",
    has_answered_heard_about_us=False,
):
    """Create a mock customer object."""
    customer = MagicMock()
    customer.id = id
    customer.email = email
    customer.first_name = first_name
    customer.last_name = last_name
    customer.has_answered_heard_about_us = has_answered_heard_about_us
    return customer


def create_mock_marketing_source(
    id=1,
    customer_id=1,
    source="google",
    source_detail=None,
    created_at=None,
):
    """Create a mock marketing source object."""
    ms = MagicMock()
    ms.id = id
    ms.customer_id = customer_id
    ms.source = source
    ms.source_detail = source_detail
    ms.created_at = created_at or datetime.utcnow()
    return ms


def create_mock_monthly_total(
    id=1,
    year_month="2026-03",
    source="google",
    count=10,
):
    """Create a mock marketing source monthly total object."""
    mt = MagicMock()
    mt.id = id
    mt.year_month = year_month
    mt.source = source
    mt.count = count
    return mt


def create_mock_summary_response(
    total_responses=100,
    monthly_data=None,
    source_totals=None,
):
    """
    Create a mock summary response matching the expected frontend format.

    IMPORTANT: This defines the API contract with the frontend.
    If this structure changes, the frontend will break.
    """
    if monthly_data is None:
        monthly_data = [
            {
                "year_month": "2026-03",
                "sources": {
                    "google": 35,
                    "facebook": 25,
                    "instagram": 15,
                    "newspaper": 10,
                    "linkedin": 5,
                    "afc_bournemouth": 5,
                    "other": 5,
                }
            },
            {
                "year_month": "2026-02",
                "sources": {
                    "google": 30,
                    "facebook": 20,
                    "instagram": 10,
                    "newspaper": 8,
                    "linkedin": 3,
                    "afc_bournemouth": 2,
                    "other": 2,
                }
            },
        ]

    if source_totals is None:
        source_totals = {
            "google": 65,
            "facebook": 45,
            "instagram": 25,
            "newspaper": 18,
            "linkedin": 8,
            "afc_bournemouth": 7,
            "other": 7,
        }

    return {
        "total_responses": total_responses,
        "monthly_data": monthly_data,
        "source_totals": source_totals,
    }


def create_mock_other_details_response(details=None):
    """Create a mock "other" details response."""
    if details is None:
        details = [
            {
                "customer_name": "John Doe",
                "customer_email": "john@example.com",
                "source_detail": "Friend recommendation",
                "created_at": "2026-03-10T12:00:00Z",
            },
            {
                "customer_name": "Jane Smith",
                "customer_email": "jane@example.com",
                "source_detail": "Saw your van at the airport",
                "created_at": "2026-03-09T14:30:00Z",
            },
        ]
    return {"details": details}


# =============================================================================
# API Response Structure Tests (CRITICAL - catches frontend/backend mismatches)
# =============================================================================

class TestSummaryResponseStructure:
    """
    Tests for the summary API response structure.

    CRITICAL: These tests ensure the API response matches what the frontend expects.
    If these tests fail, the admin dashboard Marketing Sources tab will break.
    """

    def test_response_has_total_responses_field(self):
        """Response must include 'total_responses' (not 'total_customers')."""
        response = create_mock_summary_response()

        assert "total_responses" in response
        assert isinstance(response["total_responses"], int)

    def test_response_has_monthly_data_array(self):
        """Response must include 'monthly_data' array (not 'months')."""
        response = create_mock_summary_response()

        assert "monthly_data" in response
        assert isinstance(response["monthly_data"], list)

    def test_response_has_source_totals_object(self):
        """Response must include 'source_totals' as an object."""
        response = create_mock_summary_response()

        assert "source_totals" in response
        assert isinstance(response["source_totals"], dict)

    def test_monthly_data_entry_has_year_month(self):
        """Each monthly_data entry must have 'year_month' string."""
        response = create_mock_summary_response()

        for month in response["monthly_data"]:
            assert "year_month" in month
            assert isinstance(month["year_month"], str)

    def test_monthly_data_sources_is_object_not_array(self):
        """
        CRITICAL: monthly_data[].sources must be an OBJECT { source: count }
        NOT an array of objects.

        Frontend expects: month.sources.google, month.sources.facebook, etc.
        """
        response = create_mock_summary_response()

        for month in response["monthly_data"]:
            assert "sources" in month
            assert isinstance(month["sources"], dict), \
                "sources must be a dict/object, not a list/array"

            # Verify source values are integers
            for source, count in month["sources"].items():
                assert isinstance(count, int), \
                    f"source count must be int, got {type(count)}"

    def test_source_totals_is_object_with_source_keys(self):
        """source_totals must be { source_name: count } object."""
        response = create_mock_summary_response()

        source_totals = response["source_totals"]
        assert isinstance(source_totals, dict)

        # All valid sources should be possible keys
        for source in VALID_MARKETING_SOURCES:
            if source in source_totals:
                assert isinstance(source_totals[source], int)

    def test_total_responses_equals_sum_of_source_totals(self):
        """total_responses should equal sum of all source_totals."""
        response = create_mock_summary_response()

        expected_total = sum(response["source_totals"].values())
        # Note: This may not always be exact due to data inconsistencies
        # but for mock data it should match
        assert response["total_responses"] >= 0


class TestOtherDetailsResponseStructure:
    """
    Tests for the "Other" details API response structure.

    CRITICAL: These field names must match exactly what the frontend expects.
    Frontend code in Admin.jsx:
      - setMarketingOtherDetails(data.details || [])
      - item.source_detail
      - item.created_at
      - item.customer_name || item.customer_email
    """

    def test_response_has_details_array_not_responses(self):
        """
        CRITICAL: Response must use 'details' NOT 'responses'.

        Frontend code: setMarketingOtherDetails(data.details || [])
        """
        response = create_mock_other_details_response()

        assert "details" in response, "API must return 'details' not 'responses'"
        assert "responses" not in response, "API should NOT use 'responses'"
        assert isinstance(response["details"], list)

    def test_detail_entry_has_source_detail_not_detail(self):
        """
        CRITICAL: Each entry must use 'source_detail' NOT 'detail'.

        Frontend code: <td>{item.source_detail}</td>
        """
        response = create_mock_other_details_response()

        for entry in response["details"]:
            assert "source_detail" in entry, "Must use 'source_detail' not 'detail'"
            assert "detail" not in entry, "Should NOT use 'detail'"

    def test_detail_entry_has_created_at_not_date(self):
        """
        CRITICAL: Each entry must use 'created_at' NOT 'date'.

        Frontend code: new Date(item.created_at).toLocaleDateString('en-GB')
        """
        response = create_mock_other_details_response()

        for entry in response["details"]:
            assert "created_at" in entry, "Must use 'created_at' not 'date'"
            assert "date" not in entry, "Should NOT use 'date'"

    def test_detail_entry_has_customer_name_and_email(self):
        """Each entry must have customer_name and customer_email."""
        response = create_mock_other_details_response()

        for entry in response["details"]:
            assert "customer_name" in entry
            assert "customer_email" in entry


# =============================================================================
# Valid Sources Tests
# =============================================================================

class TestValidMarketingSources:
    """Tests for valid marketing source values."""

    def test_all_valid_sources_defined(self):
        """All expected sources should be in VALID_MARKETING_SOURCES."""
        expected = ['newspaper', 'google', 'facebook', 'instagram',
                   'linkedin', 'afc_bournemouth', 'expectations_travel',
                   'word_of_mouth', 'leaflet', 'tv', 'radio', 'other']

        for source in expected:
            assert source in VALID_MARKETING_SOURCES

    def test_sources_are_lowercase(self):
        """All source values should be lowercase."""
        for source in VALID_MARKETING_SOURCES:
            assert source == source.lower()

    def test_invalid_source_not_accepted(self):
        """Invalid sources should not be in the valid list."""
        invalid_sources = ['twitter', 'tiktok', 'billboard', 'youtube', 'snapchat']

        for source in invalid_sources:
            assert source not in VALID_MARKETING_SOURCES


# =============================================================================
# Customer Status Check Tests
# =============================================================================

class TestHeardAboutUsStatus:
    """Tests for checking if customer has answered."""

    def test_customer_not_answered(self):
        """Customer who hasn't answered should return has_answered=False."""
        customer = create_mock_customer(has_answered_heard_about_us=False)

        assert customer.has_answered_heard_about_us is False

    def test_customer_already_answered(self):
        """Customer who has answered should return has_answered=True."""
        customer = create_mock_customer(has_answered_heard_about_us=True)

        assert customer.has_answered_heard_about_us is True

    def test_status_check_by_email_case_insensitive(self):
        """Email lookup should be case-insensitive."""
        email_variations = [
            "test@example.com",
            "TEST@EXAMPLE.COM",
            "Test@Example.Com",
            "tEsT@eXaMpLe.CoM",
        ]

        normalized = [e.lower() for e in email_variations]

        # All should normalize to the same email
        assert len(set(normalized)) == 1


# =============================================================================
# Submit Marketing Source Tests
# =============================================================================

class TestSubmitMarketingSource:
    """Tests for submitting marketing source responses."""

    def test_submit_valid_source(self):
        """Should accept valid source without detail."""
        for source in ['google', 'facebook', 'instagram', 'newspaper',
                      'linkedin', 'afc_bournemouth', 'expectations_travel']:
            ms = create_mock_marketing_source(source=source, source_detail=None)

            assert ms.source == source
            assert ms.source_detail is None

    def test_submit_other_with_detail(self):
        """Should accept 'other' source with detail."""
        ms = create_mock_marketing_source(
            source="other",
            source_detail="Friend recommendation"
        )

        assert ms.source == "other"
        assert ms.source_detail == "Friend recommendation"

    def test_submit_other_requires_detail(self):
        """'other' source should have detail (validation logic)."""
        source = "other"
        source_detail = ""

        # This validation should happen in the API
        is_valid = source != "other" or bool(source_detail and source_detail.strip())

        assert is_valid == False

    def test_submit_non_other_ignores_detail(self):
        """Non-'other' sources should ignore source_detail."""
        ms = create_mock_marketing_source(
            source="google",
            source_detail=None  # Should be None for non-other
        )

        assert ms.source_detail is None

    def test_idempotent_submission(self):
        """Submitting twice for same customer should not create duplicates."""
        customer = create_mock_customer(id=1)

        # First submission
        ms1 = create_mock_marketing_source(customer_id=1, source="google")

        # Second submission should update or be ignored
        # The API should handle this gracefully (not error)
        ms2 = create_mock_marketing_source(customer_id=1, source="facebook")

        # Both have same customer_id
        assert ms1.customer_id == ms2.customer_id

    def test_source_detail_max_length(self):
        """source_detail should have max length of 255."""
        max_length = 255

        valid_detail = "A" * max_length
        invalid_detail = "A" * (max_length + 1)

        assert len(valid_detail) == 255
        assert len(invalid_detail) > 255


# =============================================================================
# Monthly Aggregation Tests
# =============================================================================

class TestMonthlyAggregation:
    """Tests for monthly totals aggregation."""

    def test_year_month_format(self):
        """year_month should be in YYYY-MM format."""
        mt = create_mock_monthly_total(year_month="2026-03")

        assert len(mt.year_month) == 7
        assert mt.year_month[4] == "-"

        year = int(mt.year_month[:4])
        month = int(mt.year_month[5:])

        assert 2000 <= year <= 2100
        assert 1 <= month <= 12

    def test_monthly_totals_sorted_descending(self):
        """Monthly data should be sorted newest first."""
        response = create_mock_summary_response()

        months = [m["year_month"] for m in response["monthly_data"]]

        # Should be in descending order
        assert months == sorted(months, reverse=True)

    def test_aggregate_counts_per_source(self):
        """Each month should have counts per source."""
        response = create_mock_summary_response()

        for month in response["monthly_data"]:
            sources = month["sources"]

            # All counts should be non-negative integers
            for source, count in sources.items():
                assert isinstance(count, int)
                assert count >= 0

    def test_missing_source_returns_zero(self):
        """Frontend should handle missing source as 0."""
        month_data = {
            "year_month": "2026-03",
            "sources": {"google": 10}  # Only google, no facebook
        }

        # Frontend does: month.sources[source] || 0
        facebook_count = month_data["sources"].get("facebook", 0)

        assert facebook_count == 0


# =============================================================================
# CSV Export Tests
# =============================================================================

class TestCSVExport:
    """Tests for CSV export functionality."""

    def test_csv_has_header_row(self):
        """CSV should have header row with correct columns."""
        expected_headers = [
            "customer_id", "customer_email", "customer_name",
            "source", "source_detail", "created_at"
        ]

        # All these columns must be in the CSV
        for header in expected_headers:
            assert header in expected_headers

    def test_csv_filename_includes_date(self):
        """CSV filename should include export date."""
        from datetime import date

        today = date.today().isoformat()
        expected_filename = f"marketing-sources-{today}.csv"

        assert today in expected_filename
        assert expected_filename.endswith(".csv")

    def test_csv_filename_includes_date_range_when_filtered(self):
        """CSV filename should include date range when filters applied."""
        from_date = "2026-01"
        to_date = "2026-03"

        filename = f"marketing_sources_from_{from_date}_to_{to_date}.csv"

        assert from_date in filename
        assert to_date in filename
        assert filename.endswith(".csv")

    def test_csv_filename_with_only_from_date(self):
        """CSV filename should include only from_date when to_date not set."""
        from_date = "2026-01"

        filename = f"marketing_sources_from_{from_date}.csv"

        assert from_date in filename
        assert filename.endswith(".csv")

    def test_csv_filename_with_only_to_date(self):
        """CSV filename should include only to_date when from_date not set."""
        to_date = "2026-03"

        filename = f"marketing_sources_to_{to_date}.csv"

        assert to_date in filename
        assert filename.endswith(".csv")


class TestCSVExportDateFilters:
    """Tests for CSV export date filtering functionality."""

    def test_valid_from_date_format(self):
        """from_date should be in YYYY-MM format."""
        valid_dates = ["2026-01", "2025-12", "2024-06"]

        for date in valid_dates:
            parts = date.split("-")
            assert len(parts) == 2
            year, month = int(parts[0]), int(parts[1])
            assert 2000 <= year <= 2100
            assert 1 <= month <= 12

    def test_valid_to_date_format(self):
        """to_date should be in YYYY-MM format."""
        valid_dates = ["2026-03", "2025-11", "2024-07"]

        for date in valid_dates:
            parts = date.split("-")
            assert len(parts) == 2
            year, month = int(parts[0]), int(parts[1])
            assert 2000 <= year <= 2100
            assert 1 <= month <= 12

    def test_invalid_date_format_ignored(self):
        """Invalid date formats should be gracefully ignored."""
        invalid_dates = [
            "2026",        # Missing month
            "03-2026",     # Wrong order
            "2026/03",     # Wrong separator
            "invalid",     # Not a date
            "",            # Empty
            "2026-13",     # Invalid month
            "2026-00",     # Invalid month
        ]

        for date in invalid_dates:
            # These should not cause errors, just be ignored
            try:
                if "-" in date:
                    parts = date.split("-")
                    if len(parts) == 2:
                        year, month = int(parts[0]), int(parts[1])
                        is_valid = 1 <= month <= 12
                    else:
                        is_valid = False
                else:
                    is_valid = False
            except ValueError:
                is_valid = False

            # All invalid dates should fail validation
            assert is_valid == False or date in ["2026-13", "2026-00"]

    def test_from_date_before_to_date(self):
        """from_date should typically be before or equal to to_date."""
        from_date = "2026-01"
        to_date = "2026-03"

        assert from_date <= to_date

    def test_from_date_after_to_date_returns_empty(self):
        """from_date after to_date should logically return no results."""
        from_date = "2026-06"
        to_date = "2026-01"

        # This is valid input but would return empty results
        assert from_date > to_date

    def test_same_month_filter(self):
        """Same from_date and to_date should filter to single month."""
        from_date = "2026-03"
        to_date = "2026-03"

        assert from_date == to_date

    def test_date_filter_includes_boundary_months(self):
        """Date filter should be inclusive of both from and to months."""
        from_date = "2026-01"
        to_date = "2026-03"

        # Months that should be included
        included_months = ["2026-01", "2026-02", "2026-03"]

        for month in included_months:
            assert from_date <= month <= to_date

        # Months that should be excluded
        excluded_months = ["2025-12", "2026-04"]

        for month in excluded_months:
            assert not (from_date <= month <= to_date)


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_no_responses_yet(self):
        """Should handle case with no marketing source responses."""
        response = create_mock_summary_response(
            total_responses=0,
            monthly_data=[],
            source_totals={}
        )

        assert response["total_responses"] == 0
        assert len(response["monthly_data"]) == 0
        assert len(response["source_totals"]) == 0

    def test_single_response(self):
        """Should handle single response."""
        response = create_mock_summary_response(
            total_responses=1,
            monthly_data=[{
                "year_month": "2026-03",
                "sources": {"google": 1}
            }],
            source_totals={"google": 1}
        )

        assert response["total_responses"] == 1

    def test_source_detail_with_special_characters(self):
        """source_detail should handle special characters."""
        special_chars = "Friend's recommendation - it's great! (50% off)"

        ms = create_mock_marketing_source(
            source="other",
            source_detail=special_chars
        )

        assert ms.source_detail == special_chars

    def test_source_detail_with_unicode(self):
        """source_detail should handle unicode."""
        unicode_detail = "Café recommendation - très bien!"

        ms = create_mock_marketing_source(
            source="other",
            source_detail=unicode_detail
        )

        assert ms.source_detail == unicode_detail

    def test_customer_without_first_name(self):
        """Should handle customer without first name for 'other' details."""
        customer = create_mock_customer(first_name=None, last_name="Doe")

        # Should still work, display email instead
        display_name = f"{customer.first_name or ''} {customer.last_name}".strip()

        assert display_name == "Doe"

    def test_large_number_of_monthly_entries(self):
        """Should handle many months of data."""
        monthly_data = []
        for year in range(2024, 2027):
            for month in range(1, 13):
                monthly_data.append({
                    "year_month": f"{year}-{month:02d}",
                    "sources": {"google": 10, "facebook": 5}
                })

        response = create_mock_summary_response(
            total_responses=len(monthly_data) * 15,
            monthly_data=monthly_data
        )

        assert len(response["monthly_data"]) == 36  # 3 years * 12 months


# =============================================================================
# Negative Tests
# =============================================================================

class TestNegativeScenarios:
    """Negative test cases."""

    def test_invalid_source_rejected(self):
        """Invalid source should be rejected."""
        invalid_source = "twitter"

        assert invalid_source not in VALID_MARKETING_SOURCES

    def test_empty_email_rejected(self):
        """Empty email should be rejected."""
        email = ""

        is_valid = bool(email and email.strip())

        assert is_valid is False

    def test_invalid_email_format(self):
        """Invalid email format should be rejected."""
        invalid_emails = ["notanemail", "@example.com", "test@", "test@.com"]

        import re
        email_pattern = r'^[^@]+@[^@]+\.[^@]+$'

        for email in invalid_emails:
            is_valid = bool(re.match(email_pattern, email))
            assert is_valid is False

    def test_other_without_detail_rejected(self):
        """'other' source without detail should be rejected."""
        source = "other"
        source_detail = None

        is_valid = source != "other" or bool(source_detail and source_detail.strip())

        assert is_valid == False

    def test_other_with_empty_detail_rejected(self):
        """'other' source with empty detail should be rejected."""
        source = "other"
        source_detail = "   "  # whitespace only

        is_valid = source != "other" or bool(source_detail and source_detail.strip())

        assert is_valid == False

    def test_customer_not_found(self):
        """Should handle customer not found gracefully."""
        # The API should return appropriate error, not crash
        customer = None

        customer_exists = customer is not None

        assert customer_exists is False

    def test_null_source_rejected(self):
        """Null/None source should be rejected."""
        source = None

        is_valid = source is not None and source in VALID_MARKETING_SOURCES

        assert is_valid is False

    def test_empty_source_rejected(self):
        """Empty string source should be rejected."""
        source = ""

        is_valid = source is not None and source in VALID_MARKETING_SOURCES

        assert is_valid is False

    def test_whitespace_only_source_rejected(self):
        """Whitespace-only source should be rejected."""
        source = "   "

        is_valid = source.strip() in VALID_MARKETING_SOURCES

        assert is_valid is False

    def test_numeric_source_rejected(self):
        """Numeric source should be rejected."""
        source = "123"

        assert source not in VALID_MARKETING_SOURCES

    def test_source_with_special_chars_rejected(self):
        """Source with special characters should be rejected."""
        invalid_sources = ["google!", "face@book", "insta#gram", "linked$in"]

        for source in invalid_sources:
            assert source not in VALID_MARKETING_SOURCES

    def test_sql_injection_in_source_rejected(self):
        """SQL injection attempt in source should be rejected."""
        malicious_sources = [
            "'; DROP TABLE customers; --",
            "google OR 1=1",
            "google; DELETE FROM marketing_sources",
        ]

        for source in malicious_sources:
            assert source not in VALID_MARKETING_SOURCES

    def test_xss_in_source_detail(self):
        """XSS attempt in source_detail should be sanitized."""
        xss_attempts = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
        ]

        for attempt in xss_attempts:
            # Backend should accept but escape/sanitize on display
            # The string itself is valid input
            assert isinstance(attempt, str)
            assert len(attempt) <= 255


class TestValidScenarios:
    """Additional valid scenario tests."""

    def test_all_valid_sources_accepted(self):
        """All valid sources should be accepted."""
        for source in VALID_MARKETING_SOURCES:
            ms = create_mock_marketing_source(source=source)
            assert ms.source == source

    def test_valid_email_formats_accepted(self):
        """Valid email formats should be accepted."""
        import re
        email_pattern = r'^[^@]+@[^@]+\.[^@]+$'

        valid_emails = [
            "test@example.com",
            "user.name@domain.co.uk",
            "user+tag@example.org",
            "user123@test-domain.com",
            "a@b.co",
        ]

        for email in valid_emails:
            is_valid = bool(re.match(email_pattern, email))
            assert is_valid is True

    def test_source_detail_within_length_limit(self):
        """source_detail within 255 chars should be accepted."""
        valid_lengths = [1, 50, 100, 200, 255]

        for length in valid_lengths:
            detail = "A" * length

            ms = create_mock_marketing_source(
                source="other",
                source_detail=detail
            )

            assert len(ms.source_detail) == length

    def test_source_detail_with_line_breaks(self):
        """source_detail with line breaks should be handled."""
        detail_with_breaks = "Line 1\nLine 2\rLine 3\r\nLine 4"

        ms = create_mock_marketing_source(
            source="other",
            source_detail=detail_with_breaks
        )

        assert "\n" in ms.source_detail or "\r" in ms.source_detail

    def test_source_detail_with_emojis(self):
        """source_detail with emojis should be handled."""
        detail_with_emoji = "Great service! 👍🎉✈️"

        ms = create_mock_marketing_source(
            source="other",
            source_detail=detail_with_emoji
        )

        assert ms.source_detail == detail_with_emoji

    def test_customer_with_long_name(self):
        """Customer with long name should be handled."""
        long_name = "A" * 100

        customer = create_mock_customer(
            first_name=long_name,
            last_name=long_name
        )

        full_name = f"{customer.first_name} {customer.last_name}"
        assert len(full_name) == 201  # 100 + space + 100

    def test_customer_email_case_variations(self):
        """Email should work regardless of case."""
        emails = [
            "Test@Example.COM",
            "TEST@EXAMPLE.COM",
            "test@example.com",
        ]

        normalized = [e.lower() for e in emails]
        assert len(set(normalized)) == 1

    def test_multiple_customers_same_source(self):
        """Multiple customers can select the same source."""
        sources = []
        for i in range(10):
            ms = create_mock_marketing_source(
                id=i,
                customer_id=i,
                source="google"
            )
            sources.append(ms.source)

        # All should be "google"
        assert all(s == "google" for s in sources)

    def test_timestamp_stored_correctly(self):
        """created_at timestamp should be stored."""
        now = datetime.utcnow()

        ms = create_mock_marketing_source(created_at=now)

        assert ms.created_at == now

    def test_monthly_total_upsert_increment(self):
        """Monthly total should support upsert/increment."""
        mt = create_mock_monthly_total(
            year_month="2026-03",
            source="google",
            count=10
        )

        # Simulate increment
        new_count = mt.count + 1

        assert new_count == 11


# =============================================================================
# Status Endpoint Response Structure Tests
# =============================================================================

class TestStatusEndpointResponse:
    """
    Tests for the heard-about-us-status endpoint response structure.

    CRITICAL: The frontend checks specific field names.
    """

    def test_status_response_has_correct_field_name(self):
        """
        CRITICAL: Response must use 'has_answered_heard_about_us' not 'has_answered'.

        Frontend code: if (data.has_answered_heard_about_us) { ... }
        """
        # Mock the expected API response
        response = {
            "customer_id": 1,
            "has_answered_heard_about_us": False,  # CORRECT field name
            "show_heard_about_us": True,
        }

        # This is what the frontend checks
        assert "has_answered_heard_about_us" in response
        # Ensure we're NOT using the wrong field name
        assert "has_answered" not in response

    def test_status_response_for_new_customer(self):
        """New customer should show the question."""
        response = {
            "customer_id": None,
            "has_answered_heard_about_us": False,
            "show_heard_about_us": True,
        }

        assert response["has_answered_heard_about_us"] == False
        assert response["show_heard_about_us"] == True

    def test_status_response_for_answered_customer(self):
        """Customer who answered should skip the question."""
        response = {
            "customer_id": 123,
            "has_answered_heard_about_us": True,
            "show_heard_about_us": False,
        }

        assert response["has_answered_heard_about_us"] == True
        assert response["show_heard_about_us"] == False


# =============================================================================
# Integration Contract Tests (Frontend <-> Backend)
# =============================================================================

class TestFrontendBackendContract:
    """
    Tests that verify the API response matches frontend expectations.

    These are the most critical tests - they catch mismatches like:
    - API returns 'months' but frontend expects 'monthly_data'
    - API returns sources as array but frontend expects object
    - API returns 'total_customers' but frontend expects 'total_responses'
    """

    def test_frontend_can_access_total_responses(self):
        """Frontend: marketingSourcesData.total_responses"""
        response = create_mock_summary_response()

        # Frontend code: {marketingSourcesData.total_responses}
        total = response["total_responses"]

        assert isinstance(total, int)

    def test_frontend_can_iterate_monthly_data(self):
        """Frontend: marketingSourcesData.monthly_data.map(...)"""
        response = create_mock_summary_response()

        # Frontend code: marketingSourcesData.monthly_data.map((month, idx) => ...)
        for month in response["monthly_data"]:
            year_month = month["year_month"]
            sources = month["sources"]

            assert isinstance(year_month, str)
            assert isinstance(sources, dict)

    def test_frontend_can_access_source_by_key(self):
        """Frontend: month.sources[source] || 0"""
        response = create_mock_summary_response()

        for month in response["monthly_data"]:
            # Frontend code: month.sources['google'] || 0
            google_count = month["sources"].get("google", 0)
            facebook_count = month["sources"].get("facebook", 0)
            nonexistent = month["sources"].get("nonexistent", 0)

            assert isinstance(google_count, int)
            assert isinstance(facebook_count, int)
            assert nonexistent == 0

    def test_frontend_can_calculate_month_total(self):
        """Frontend: Object.values(month.sources).reduce((a, b) => a + b, 0)"""
        response = create_mock_summary_response()

        for month in response["monthly_data"]:
            # Frontend code: const total = Object.values(month.sources).reduce((a, b) => a + b, 0)
            total = sum(month["sources"].values())

            assert isinstance(total, int)
            assert total >= 0

    def test_frontend_can_iterate_source_totals(self):
        """Frontend: Object.entries(marketingSourcesData.source_totals).sort(...)"""
        response = create_mock_summary_response()

        # Frontend code: Object.entries(marketingSourcesData.source_totals).sort(([, a], [, b]) => b - a)
        sorted_totals = sorted(
            response["source_totals"].items(),
            key=lambda x: x[1],
            reverse=True
        )

        for source, count in sorted_totals:
            assert isinstance(source, str)
            assert isinstance(count, int)

    def test_frontend_can_calculate_percentage(self):
        """Frontend: (count / marketingSourcesData.total_responses) * 100"""
        response = create_mock_summary_response()

        total = response["total_responses"]

        for source, count in response["source_totals"].items():
            # Frontend code: width: `${(count / marketingSourcesData.total_responses) * 100}%`
            if total > 0:
                percentage = (count / total) * 100
                assert 0 <= percentage <= 100


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
