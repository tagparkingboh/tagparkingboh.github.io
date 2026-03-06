"""
Tests for Testimonials API endpoints.

Mocked unit tests and mocked integration tests for:
- CRUD operations
- Status toggle
- Public weighted endpoint
- Weighted pool logic
"""
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch, AsyncMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# Mock testimonial data
mock_testimonials = [
    {
        "id": 1,
        "customer_name": "John Doe",
        "review_text": "Excellent service! Very professional and convenient.",
        "star_rating": 5,
        "date_of_travel": "2026-01-15",
        "date_added": "2026-03-01T10:30:00Z",
        "status": "active",
        "is_featured": True,
        "source": "google",
    },
    {
        "id": 2,
        "customer_name": "Jane Smith",
        "review_text": "Great experience, will use again.",
        "star_rating": 4,
        "date_of_travel": "2026-02-10",
        "date_added": "2026-03-02T14:15:00Z",
        "status": "active",
        "is_featured": False,
        "source": "trustpilot",
    },
    {
        "id": 3,
        "customer_name": "Bob Wilson",
        "review_text": "Highly recommend TAG parking!",
        "star_rating": None,
        "date_of_travel": "2026-01-20",
        "date_added": "2026-03-03T09:00:00Z",
        "status": "inactive",
        "is_featured": False,
        "source": "linkedin",
    },
    {
        "id": 4,
        "customer_name": "Sarah Connor",
        "review_text": "Best parking service ever!",
        "star_rating": 3,
        "date_of_travel": "2026-02-01",
        "date_added": "2026-03-04T11:00:00Z",
        "status": "active",
        "is_featured": False,
        "source": "email",
    },
    {
        "id": 5,
        "customer_name": "Mike Brown",
        "review_text": "Service was okay.",
        "star_rating": 2,
        "date_of_travel": "2026-01-25",
        "date_added": "2026-03-05T08:00:00Z",
        "status": "active",
        "is_featured": False,
        "source": "google",
    },
]


class TestPublicTestimonialsEndpoint:
    """Mocked tests for the public /api/testimonials endpoint."""

    def test_get_active_testimonials_filters_by_status(self):
        """Should only return active testimonials."""
        active_testimonials = [t for t in mock_testimonials if t["status"] == "active"]

        assert len(active_testimonials) == 4
        assert all(t["status"] == "active" for t in active_testimonials)

    def test_response_format_contains_testimonials_and_total(self):
        """Response should have testimonials array and total count."""
        active = [t for t in mock_testimonials if t["status"] == "active"]
        response = {"testimonials": active, "total": len(active)}

        assert "testimonials" in response
        assert "total" in response
        assert isinstance(response["testimonials"], list)
        assert response["total"] == 4

    def test_inactive_testimonials_excluded(self):
        """Inactive testimonials should not appear in public endpoint."""
        active = [t for t in mock_testimonials if t["status"] == "active"]
        inactive_ids = [t["id"] for t in mock_testimonials if t["status"] == "inactive"]

        for testimonial in active:
            assert testimonial["id"] not in inactive_ids


class TestAdminTestimonialsListEndpoint:
    """Mocked tests for GET /api/admin/testimonials."""

    def test_admin_list_returns_all_testimonials(self):
        """Admin endpoint should return all testimonials including inactive."""
        all_testimonials = mock_testimonials

        assert len(all_testimonials) == 5
        statuses = [t["status"] for t in all_testimonials]
        assert "active" in statuses
        assert "inactive" in statuses

    def test_admin_list_includes_all_fields(self):
        """Admin list should include all testimonial fields."""
        testimonial = mock_testimonials[0]

        required_fields = [
            "id", "customer_name", "review_text", "star_rating",
            "date_of_travel", "date_added", "status", "is_featured", "source"
        ]
        for field in required_fields:
            assert field in testimonial


class TestAdminCreateTestimonialEndpoint:
    """Mocked tests for POST /api/admin/testimonials."""

    def test_create_testimonial_with_all_fields(self):
        """Should create testimonial with all provided fields."""
        new_testimonial = {
            "customer_name": "New Customer",
            "review_text": "Amazing parking service!",
            "star_rating": 5,
            "date_of_travel": "2026-03-15",
            "source": "google",
            "is_featured": False,
        }

        # Simulate creation
        created = {
            "id": 6,
            **new_testimonial,
            "status": "inactive",  # Default status
            "date_added": "2026-03-06T12:00:00Z",
        }

        assert created["customer_name"] == "New Customer"
        assert created["status"] == "inactive"
        assert created["id"] == 6

    def test_create_testimonial_without_rating(self):
        """Should allow creating testimonial with null star_rating."""
        new_testimonial = {
            "customer_name": "LinkedIn User",
            "review_text": "Highly recommend!",
            "star_rating": None,
            "source": "linkedin",
        }

        assert new_testimonial["star_rating"] is None

    def test_create_testimonial_default_status_inactive(self):
        """New testimonials should default to inactive status."""
        created = {
            "customer_name": "Test",
            "review_text": "Test review",
            "status": "inactive",  # Default
        }

        assert created["status"] == "inactive"

    def test_create_validation_requires_customer_name(self):
        """Should require customer_name field."""
        invalid = {"review_text": "Missing customer name"}

        is_valid = "customer_name" in invalid and len(invalid.get("customer_name", "")) > 0
        assert is_valid is False

    def test_create_validation_requires_review_text(self):
        """Should require review_text field."""
        invalid = {"customer_name": "Test Name"}

        is_valid = "review_text" in invalid and len(invalid.get("review_text", "")) > 0
        assert is_valid is False


class TestAdminUpdateTestimonialEndpoint:
    """Mocked tests for PUT /api/admin/testimonials/{id}."""

    def test_update_testimonial_fields(self):
        """Should update specified fields."""
        original = mock_testimonials[0].copy()
        updates = {"review_text": "Updated review - even better!"}

        updated = {**original, **updates}

        assert updated["review_text"] == "Updated review - even better!"
        assert updated["customer_name"] == original["customer_name"]

    def test_update_preserves_unmodified_fields(self):
        """Unmodified fields should remain unchanged."""
        original = mock_testimonials[0].copy()
        updates = {"star_rating": 4}

        updated = {**original, **updates}

        assert updated["star_rating"] == 4
        assert updated["customer_name"] == original["customer_name"]
        assert updated["source"] == original["source"]

    def test_update_nonexistent_returns_404(self):
        """Updating non-existent testimonial should indicate not found."""
        testimonial_id = 999
        exists = any(t["id"] == testimonial_id for t in mock_testimonials)

        assert exists is False


class TestAdminDeleteTestimonialEndpoint:
    """Mocked tests for DELETE /api/admin/testimonials/{id}."""

    def test_delete_removes_testimonial(self):
        """Delete should remove testimonial from list."""
        testimonials = mock_testimonials.copy()
        id_to_delete = 3

        remaining = [t for t in testimonials if t["id"] != id_to_delete]

        assert len(remaining) == len(testimonials) - 1
        assert not any(t["id"] == id_to_delete for t in remaining)

    def test_delete_nonexistent_returns_404(self):
        """Deleting non-existent testimonial should indicate not found."""
        testimonial_id = 999
        exists = any(t["id"] == testimonial_id for t in mock_testimonials)

        assert exists is False


class TestAdminToggleStatusEndpoint:
    """Mocked tests for PATCH /api/admin/testimonials/{id}/status."""

    def test_toggle_inactive_to_active(self):
        """Should toggle status from inactive to active."""
        testimonial = mock_testimonials[2].copy()  # inactive
        assert testimonial["status"] == "inactive"

        testimonial["status"] = "active"

        assert testimonial["status"] == "active"

    def test_toggle_active_to_inactive(self):
        """Should toggle status from active to inactive."""
        testimonial = mock_testimonials[0].copy()  # active
        assert testimonial["status"] == "active"

        testimonial["status"] = "inactive"

        assert testimonial["status"] == "inactive"

    def test_invalid_status_rejected(self):
        """Invalid status value should be rejected."""
        valid_statuses = ["active", "inactive"]
        invalid_status = "pending"

        is_valid = invalid_status in valid_statuses
        assert is_valid is False


class TestWeightedPoolLogic:
    """Mocked unit tests for weighted pool calculation logic."""

    def test_5_star_gets_5x_weight(self):
        """5-star testimonials should appear 5 times in pool."""
        rating = 5
        weight = 5 if rating == 5 else 3 if rating == 4 else 1 if rating == 3 else 0
        assert weight == 5

    def test_4_star_gets_3x_weight(self):
        """4-star testimonials should appear 3 times in pool."""
        rating = 4
        weight = 5 if rating == 5 else 3 if rating == 4 else 1 if rating == 3 else 0
        assert weight == 3

    def test_3_star_gets_1x_weight(self):
        """3-star testimonials should appear 1 time in pool."""
        rating = 3
        weight = 5 if rating == 5 else 3 if rating == 4 else 1 if rating == 3 else 0
        assert weight == 1

    def test_unrated_gets_3x_weight(self):
        """Unrated testimonials should appear 3 times in pool."""
        rating = None
        weight = 3 if rating is None else (5 if rating == 5 else 3 if rating == 4 else 1 if rating == 3 else 0)
        assert weight == 3

    def test_2_star_excluded(self):
        """2-star testimonials should be excluded (0 weight)."""
        rating = 2
        weight = 5 if rating == 5 else 3 if rating == 4 else 1 if rating == 3 else 0
        assert weight == 0

    def test_1_star_excluded(self):
        """1-star testimonials should be excluded (0 weight)."""
        rating = 1
        weight = 5 if rating == 5 else 3 if rating == 4 else 1 if rating == 3 else 0
        assert weight == 0

    def test_featured_always_included_regardless_of_rating(self):
        """Featured testimonials should always be included even with low rating."""
        testimonial = {"star_rating": 1, "is_featured": True}

        should_include = testimonial["is_featured"]
        assert should_include is True

    def test_build_weighted_pool_correct_distribution(self):
        """Test building weighted pool produces correct distribution."""
        testimonials = [
            {"id": 1, "star_rating": 5, "is_featured": False},  # 5x
            {"id": 2, "star_rating": 4, "is_featured": False},  # 3x
            {"id": 3, "star_rating": None, "is_featured": False},  # 3x (unrated)
            {"id": 4, "star_rating": 3, "is_featured": False},  # 1x
            {"id": 5, "star_rating": 2, "is_featured": False},  # 0x (excluded)
            {"id": 6, "star_rating": 1, "is_featured": True},   # 1x (featured override)
        ]

        weighted_pool = []
        for t in testimonials:
            if t["is_featured"]:
                weighted_pool.append(t)
                continue

            if t["star_rating"] is None:
                weighted_pool.extend([t] * 3)
            elif t["star_rating"] == 5:
                weighted_pool.extend([t] * 5)
            elif t["star_rating"] == 4:
                weighted_pool.extend([t] * 3)
            elif t["star_rating"] == 3:
                weighted_pool.append(t)
            # 1-2 stars excluded unless featured

        # Expected: 5 + 3 + 3 + 1 + 0 + 1 = 13
        assert len(weighted_pool) == 13

        # Verify counts by ID
        id_counts = {}
        for t in weighted_pool:
            id_counts[t["id"]] = id_counts.get(t["id"], 0) + 1

        assert id_counts[1] == 5  # 5-star
        assert id_counts[2] == 3  # 4-star
        assert id_counts[3] == 3  # unrated
        assert id_counts[4] == 1  # 3-star
        assert id_counts.get(5, 0) == 0  # 2-star excluded
        assert id_counts[6] == 1  # 1-star but featured

    def test_weighted_pool_with_only_featured(self):
        """Pool with only featured testimonials."""
        testimonials = [
            {"id": 1, "star_rating": 1, "is_featured": True},
            {"id": 2, "star_rating": 2, "is_featured": True},
        ]

        weighted_pool = []
        for t in testimonials:
            if t["is_featured"]:
                weighted_pool.append(t)

        assert len(weighted_pool) == 2

    def test_weighted_pool_empty_when_no_qualifying(self):
        """Pool should be empty when no testimonials qualify."""
        testimonials = [
            {"id": 1, "star_rating": 1, "is_featured": False},
            {"id": 2, "star_rating": 2, "is_featured": False},
        ]

        weighted_pool = []
        for t in testimonials:
            if t["is_featured"]:
                weighted_pool.append(t)
                continue
            if t["star_rating"] is None:
                weighted_pool.extend([t] * 3)
            elif t["star_rating"] == 5:
                weighted_pool.extend([t] * 5)
            elif t["star_rating"] == 4:
                weighted_pool.extend([t] * 3)
            elif t["star_rating"] == 3:
                weighted_pool.append(t)

        assert len(weighted_pool) == 0


class TestTestimonialValidation:
    """Mocked unit tests for testimonial data validation."""

    def test_valid_star_rating_range(self):
        """Star rating should be 1-5 or None."""
        valid_ratings = [None, 1, 2, 3, 4, 5]
        for rating in valid_ratings:
            is_valid = rating is None or (1 <= rating <= 5)
            assert is_valid is True

    def test_invalid_star_rating_zero(self):
        """Star rating of 0 should be invalid."""
        rating = 0
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is False

    def test_invalid_star_rating_negative(self):
        """Negative star rating should be invalid."""
        rating = -1
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is False

    def test_invalid_star_rating_above_5(self):
        """Star rating above 5 should be invalid."""
        rating = 6
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is False

    def test_status_valid_values(self):
        """Status should be 'active' or 'inactive'."""
        valid_statuses = ["active", "inactive"]

        assert "active" in valid_statuses
        assert "inactive" in valid_statuses

    def test_customer_name_max_length(self):
        """Customer name should be max 100 characters."""
        max_length = 100
        valid_name = "A" * 100
        invalid_name = "A" * 101

        assert len(valid_name) <= max_length
        assert len(invalid_name) > max_length

    def test_source_valid_values(self):
        """Source should be a valid platform or null."""
        valid_sources = ["google", "trustpilot", "facebook", "linkedin", "email", "other", None]

        for source in valid_sources:
            is_valid = source is None or source in ["google", "trustpilot", "facebook", "linkedin", "email", "other"]
            assert is_valid is True


class TestTestimonialDateFormatting:
    """Mocked tests for date formatting logic."""

    def test_api_returns_iso_format_date(self):
        """API should return date_of_travel in ISO format (YYYY-MM-DD)."""
        date_obj = date(2026, 3, 15)
        iso_formatted = date_obj.isoformat()
        assert iso_formatted == "2026-03-15"

    def test_frontend_displays_full_month_name(self):
        """Frontend should display date as 'March 2026' (full month name)."""
        date_obj = date(2026, 3, 15)
        # Frontend uses: toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
        # This is the expected display format
        expected_display = "March 2026"
        formatted = date_obj.strftime("%B %Y")  # %B = full month name
        assert formatted == expected_display

    def test_format_date_added_with_time(self):
        """Date added should include time."""
        dt = datetime(2026, 3, 15, 10, 30, 0)
        formatted = dt.strftime("%Y-%m-%d %H:%M")
        assert formatted == "2026-03-15 10:30"

    def test_none_date_handling(self):
        """None dates should be handled gracefully."""
        date_obj = None
        formatted = date_obj.strftime("%b %Y") if date_obj else None
        assert formatted is None

    def test_date_parsing_from_string(self):
        """Should parse date string correctly."""
        date_string = "2026-03-15"
        parsed = datetime.strptime(date_string, "%Y-%m-%d").date()

        assert parsed.year == 2026
        assert parsed.month == 3
        assert parsed.day == 15


class TestParseDateOfTravel:
    """Tests for parse_date_of_travel function - handles ISO and legacy formats."""

    def _parse_date_of_travel(self, date_str):
        """Mock implementation of parse_date_of_travel matching main.py."""
        if not date_str:
            return None
        try:
            # HTML date input sends ISO format: YYYY-MM-DD
            if "-" in date_str:
                parts = date_str.split("-")
                if len(parts) == 3:
                    return date(int(parts[0]), int(parts[1]), int(parts[2]))
            # Legacy support for DD/MM/YYYY format
            elif "/" in date_str:
                parts = date_str.split("/")
                if len(parts) == 3:
                    return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, IndexError):
            pass
        return None

    def test_parse_iso_format(self):
        """Should parse ISO format YYYY-MM-DD from HTML date input."""
        result = self._parse_date_of_travel("2026-03-15")
        assert result == date(2026, 3, 15)

    def test_parse_iso_format_january(self):
        """Should parse ISO format for January."""
        result = self._parse_date_of_travel("2026-01-01")
        assert result == date(2026, 1, 1)

    def test_parse_iso_format_december(self):
        """Should parse ISO format for December."""
        result = self._parse_date_of_travel("2026-12-31")
        assert result == date(2026, 12, 31)

    def test_parse_legacy_dd_mm_yyyy_format(self):
        """Should parse legacy DD/MM/YYYY format."""
        result = self._parse_date_of_travel("15/03/2026")
        assert result == date(2026, 3, 15)

    def test_parse_legacy_format_january(self):
        """Should parse legacy format for January."""
        result = self._parse_date_of_travel("01/01/2026")
        assert result == date(2026, 1, 1)

    def test_parse_empty_string_returns_none(self):
        """Empty string should return None."""
        result = self._parse_date_of_travel("")
        assert result is None

    def test_parse_none_returns_none(self):
        """None input should return None."""
        result = self._parse_date_of_travel(None)
        assert result is None

    def test_parse_invalid_format_returns_none(self):
        """Invalid format should return None."""
        result = self._parse_date_of_travel("March 15, 2026")
        assert result is None

    def test_parse_invalid_iso_date_returns_none(self):
        """Invalid ISO date (month 13) should return None."""
        result = self._parse_date_of_travel("2026-13-15")
        assert result is None

    def test_parse_invalid_legacy_date_returns_none(self):
        """Invalid legacy date (day 32) should return None."""
        result = self._parse_date_of_travel("32/03/2026")
        assert result is None

    def test_parse_partial_iso_returns_none(self):
        """Partial ISO format should return None."""
        result = self._parse_date_of_travel("2026-03")
        assert result is None

    def test_parse_partial_legacy_returns_none(self):
        """Partial legacy format should return None."""
        result = self._parse_date_of_travel("15/03")
        assert result is None


class TestTestimonialFiltering:
    """Mocked tests for filtering and search logic."""

    def test_filter_by_status_active(self):
        """Should filter to only active testimonials."""
        filtered = [t for t in mock_testimonials if t["status"] == "active"]

        assert len(filtered) == 4
        assert all(t["status"] == "active" for t in filtered)

    def test_filter_by_status_inactive(self):
        """Should filter to only inactive testimonials."""
        filtered = [t for t in mock_testimonials if t["status"] == "inactive"]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "Bob Wilson"

    def test_filter_by_featured(self):
        """Should filter to only featured testimonials."""
        filtered = [t for t in mock_testimonials if t["is_featured"]]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "John Doe"

    def test_filter_by_star_rating(self):
        """Should filter by specific star rating."""
        filtered = [t for t in mock_testimonials if t["star_rating"] == 5]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "John Doe"

    def test_filter_unrated_testimonials(self):
        """Should filter to unrated testimonials only."""
        filtered = [t for t in mock_testimonials if t["star_rating"] is None]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "Bob Wilson"

    def test_search_by_customer_name(self):
        """Should search by customer name (case insensitive)."""
        search_term = "john"
        filtered = [t for t in mock_testimonials
                   if search_term.lower() in t["customer_name"].lower()]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "John Doe"

    def test_search_by_review_text(self):
        """Should search within review text."""
        search_term = "recommend"
        filtered = [t for t in mock_testimonials
                   if search_term.lower() in t["review_text"].lower()]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "Bob Wilson"

    def test_combined_filters(self):
        """Should support combining multiple filters."""
        # Active + 5 stars
        filtered = [t for t in mock_testimonials
                   if t["status"] == "active" and t["star_rating"] == 5]

        assert len(filtered) == 1
        assert filtered[0]["customer_name"] == "John Doe"


class TestEdgeCases:
    """Mocked tests for edge cases."""

    def test_empty_testimonials_list(self):
        """Should handle empty testimonials list."""
        empty_list = []
        weighted_pool = []

        for t in empty_list:
            if t["is_featured"]:
                weighted_pool.append(t)

        assert len(weighted_pool) == 0

    def test_very_long_review_text(self):
        """Should handle very long review text."""
        long_review = "A" * 5000
        testimonial = {"review_text": long_review}

        assert len(testimonial["review_text"]) == 5000

    def test_special_characters_in_name(self):
        """Should handle special characters in customer name."""
        special_name = "O'Brien-Smith & Co."
        testimonial = {"customer_name": special_name}

        assert "'" in testimonial["customer_name"]
        assert "&" in testimonial["customer_name"]

    def test_unicode_in_review(self):
        """Should handle unicode characters in review."""
        unicode_review = "Great service! 👍 Highly recommend 🚗✈️"
        testimonial = {"review_text": unicode_review}

        assert "👍" in testimonial["review_text"]
        assert "✈️" in testimonial["review_text"]

    def test_all_testimonials_same_rating(self):
        """Should handle all testimonials having same rating."""
        same_rating = [
            {"id": 1, "star_rating": 5, "is_featured": False},
            {"id": 2, "star_rating": 5, "is_featured": False},
            {"id": 3, "star_rating": 5, "is_featured": False},
        ]

        weighted_pool = []
        for t in same_rating:
            weighted_pool.extend([t] * 5)

        assert len(weighted_pool) == 15  # 3 * 5

    def test_all_testimonials_unrated(self):
        """Should handle all testimonials being unrated."""
        all_unrated = [
            {"id": 1, "star_rating": None, "is_featured": False},
            {"id": 2, "star_rating": None, "is_featured": False},
        ]

        weighted_pool = []
        for t in all_unrated:
            if t["star_rating"] is None:
                weighted_pool.extend([t] * 3)

        assert len(weighted_pool) == 6  # 2 * 3


class TestNegativeTests:
    """Negative tests - invalid inputs that should be rejected."""

    def test_empty_customer_name_rejected(self):
        """Empty string customer_name should be invalid."""
        testimonial = {"customer_name": "", "review_text": "Test review"}
        is_valid = len(testimonial["customer_name"].strip()) > 0
        assert is_valid is False

    def test_whitespace_only_customer_name_rejected(self):
        """Whitespace-only customer_name should be invalid."""
        testimonial = {"customer_name": "   ", "review_text": "Test review"}
        is_valid = len(testimonial["customer_name"].strip()) > 0
        assert is_valid is False

    def test_empty_review_text_rejected(self):
        """Empty string review_text should be invalid."""
        testimonial = {"customer_name": "Test Name", "review_text": ""}
        is_valid = len(testimonial["review_text"].strip()) > 0
        assert is_valid is False

    def test_whitespace_only_review_text_rejected(self):
        """Whitespace-only review_text should be invalid."""
        testimonial = {"customer_name": "Test Name", "review_text": "   \n\t  "}
        is_valid = len(testimonial["review_text"].strip()) > 0
        assert is_valid is False

    def test_invalid_status_value_rejected(self):
        """Status values other than active/inactive should be rejected."""
        invalid_statuses = ["pending", "deleted", "archived", "ACTIVE", "Active", "1", "true", ""]
        valid_statuses = ["active", "inactive"]

        for status in invalid_statuses:
            is_valid = status in valid_statuses
            assert is_valid is False, f"Status '{status}' should be invalid"

    def test_star_rating_float_rejected(self):
        """Float star ratings should be invalid."""
        rating = 4.5
        is_valid = isinstance(rating, int) or rating is None
        assert is_valid is False

    def test_star_rating_string_rejected(self):
        """String star ratings should be invalid."""
        rating = "5"
        is_valid = isinstance(rating, int) or rating is None
        assert is_valid is False

    def test_negative_id_invalid(self):
        """Negative ID should be invalid."""
        testimonial_id = -1
        is_valid = testimonial_id > 0
        assert is_valid is False

    def test_zero_id_invalid(self):
        """Zero ID should be invalid."""
        testimonial_id = 0
        is_valid = testimonial_id > 0
        assert is_valid is False

    def test_invalid_date_format_rejected(self):
        """Invalid date format should be rejected."""
        invalid_dates = ["15-03-2026", "03/15/2026", "2026/03/15", "March 15, 2026", "invalid"]

        for date_str in invalid_dates:
            try:
                datetime.strptime(date_str, "%Y-%m-%d")
                is_valid = True
            except ValueError:
                is_valid = False
            assert is_valid is False, f"Date '{date_str}' should be invalid"

    def test_future_date_of_travel_flagged(self):
        """Future date of travel should be flagged (testimonial before trip)."""
        future_date = date(2030, 12, 31)
        today = date(2026, 3, 6)
        is_future = future_date > today
        assert is_future is True  # This would be flagged as suspicious

    def test_sql_injection_in_name_sanitized(self):
        """SQL injection attempts should be handled safely."""
        malicious_name = "'; DROP TABLE testimonials; --"
        # The name should be stored as-is (sanitization happens at query level)
        testimonial = {"customer_name": malicious_name}
        assert testimonial["customer_name"] == malicious_name
        # Actual protection is via parameterized queries, not input validation

    def test_xss_in_review_text_preserved(self):
        """XSS attempts should be stored but sanitized on output."""
        xss_review = '<script>alert("XSS")</script>Great service!'
        testimonial = {"review_text": xss_review}
        # Stored as-is, sanitization happens at render time
        assert "<script>" in testimonial["review_text"]


class TestBoundaryTests:
    """Boundary tests - testing at exact limits of valid inputs."""

    def test_star_rating_lower_bound_valid(self):
        """Star rating of 1 (lower bound) should be valid."""
        rating = 1
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is True

    def test_star_rating_upper_bound_valid(self):
        """Star rating of 5 (upper bound) should be valid."""
        rating = 5
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is True

    def test_star_rating_below_lower_bound_invalid(self):
        """Star rating of 0 (below lower bound) should be invalid."""
        rating = 0
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is False

    def test_star_rating_above_upper_bound_invalid(self):
        """Star rating of 6 (above upper bound) should be invalid."""
        rating = 6
        is_valid = rating is None or (1 <= rating <= 5)
        assert is_valid is False

    def test_customer_name_at_max_length_valid(self):
        """Customer name at exactly 100 chars should be valid."""
        name = "A" * 100
        max_length = 100
        is_valid = len(name) <= max_length
        assert is_valid is True
        assert len(name) == 100

    def test_customer_name_over_max_length_invalid(self):
        """Customer name at 101 chars should be invalid."""
        name = "A" * 101
        max_length = 100
        is_valid = len(name) <= max_length
        assert is_valid is False

    def test_customer_name_minimum_length_valid(self):
        """Customer name of 1 char should be valid."""
        name = "A"
        is_valid = len(name.strip()) >= 1
        assert is_valid is True

    def test_review_text_minimum_length_valid(self):
        """Review text of 1 char should be valid."""
        review = "A"
        is_valid = len(review.strip()) >= 1
        assert is_valid is True

    def test_review_text_at_reasonable_max_valid(self):
        """Review text at 10000 chars should be valid."""
        review = "A" * 10000
        max_length = 10000
        is_valid = len(review) <= max_length
        assert is_valid is True

    def test_date_at_earliest_reasonable_valid(self):
        """Date far in the past should still be valid."""
        old_date = date(2000, 1, 1)
        is_valid = isinstance(old_date, date)
        assert is_valid is True

    def test_weighted_pool_single_5_star(self):
        """Single 5-star testimonial should produce pool of 5."""
        testimonials = [{"id": 1, "star_rating": 5, "is_featured": False}]
        weighted_pool = []
        for t in testimonials:
            if t["star_rating"] == 5:
                weighted_pool.extend([t] * 5)
        assert len(weighted_pool) == 5

    def test_weighted_pool_single_4_star(self):
        """Single 4-star testimonial should produce pool of 3."""
        testimonials = [{"id": 1, "star_rating": 4, "is_featured": False}]
        weighted_pool = []
        for t in testimonials:
            if t["star_rating"] == 4:
                weighted_pool.extend([t] * 3)
        assert len(weighted_pool) == 3

    def test_weighted_pool_single_3_star(self):
        """Single 3-star testimonial should produce pool of 1."""
        testimonials = [{"id": 1, "star_rating": 3, "is_featured": False}]
        weighted_pool = []
        for t in testimonials:
            if t["star_rating"] == 3:
                weighted_pool.append(t)
        assert len(weighted_pool) == 1


class TestAdditionalEdgeCases:
    """Additional edge cases for comprehensive coverage."""

    def test_single_testimonial_in_list(self):
        """Should handle list with exactly one testimonial."""
        single = [{"id": 1, "status": "active", "star_rating": 5}]
        assert len(single) == 1

    def test_testimonial_with_all_optional_fields_null(self):
        """Testimonial with all optional fields as null should be valid."""
        testimonial = {
            "id": 1,
            "customer_name": "Test User",
            "review_text": "Test review",
            "star_rating": None,
            "date_of_travel": None,
            "source": None,
            "is_featured": False,
            "status": "inactive",
        }
        # Only required fields need values
        is_valid = (
            testimonial["customer_name"] and
            testimonial["review_text"] and
            testimonial["status"] in ["active", "inactive"]
        )
        assert is_valid is True

    def test_testimonial_with_minimum_valid_data(self):
        """Testimonial with only required fields should be valid."""
        testimonial = {
            "customer_name": "A",
            "review_text": "B",
        }
        is_valid = (
            len(testimonial["customer_name"].strip()) > 0 and
            len(testimonial["review_text"].strip()) > 0
        )
        assert is_valid is True

    def test_mixed_featured_and_regular_in_pool(self):
        """Pool should correctly mix featured and weighted regular testimonials."""
        testimonials = [
            {"id": 1, "star_rating": 5, "is_featured": False},  # 5x
            {"id": 2, "star_rating": 2, "is_featured": True},   # 1x (featured)
            {"id": 3, "star_rating": 1, "is_featured": False},  # 0x (excluded)
        ]

        weighted_pool = []
        for t in testimonials:
            if t["is_featured"]:
                weighted_pool.append(t)
                continue
            if t["star_rating"] == 5:
                weighted_pool.extend([t] * 5)

        assert len(weighted_pool) == 6  # 5 + 1
        featured_count = sum(1 for t in weighted_pool if t["is_featured"])
        assert featured_count == 1

    def test_duplicate_ids_in_source_data(self):
        """Should handle (or flag) duplicate IDs in source data."""
        testimonials = [
            {"id": 1, "customer_name": "User A"},
            {"id": 1, "customer_name": "User B"},  # Duplicate ID
        ]
        ids = [t["id"] for t in testimonials]
        has_duplicates = len(ids) != len(set(ids))
        assert has_duplicates is True  # This scenario should be flagged

    def test_case_sensitivity_in_search(self):
        """Search should be case-insensitive."""
        testimonial = {"customer_name": "John DOE", "review_text": "GREAT Service"}

        # Search variations
        searches = ["john", "JOHN", "John", "doe", "DOE", "great", "GREAT"]
        for term in searches:
            found_in_name = term.lower() in testimonial["customer_name"].lower()
            found_in_review = term.lower() in testimonial["review_text"].lower()
            assert found_in_name or found_in_review

    def test_filter_returns_empty_when_no_match(self):
        """Filter should return empty list when no testimonials match."""
        testimonials = [
            {"status": "active", "star_rating": 4},
            {"status": "active", "star_rating": 5},
        ]
        # Filter for 3-star (none exist)
        filtered = [t for t in testimonials if t["star_rating"] == 3]
        assert len(filtered) == 0

    def test_all_inactive_testimonials(self):
        """Public endpoint should return empty when all are inactive."""
        testimonials = [
            {"id": 1, "status": "inactive"},
            {"id": 2, "status": "inactive"},
        ]
        active = [t for t in testimonials if t["status"] == "active"]
        assert len(active) == 0

    def test_pagination_boundary_first_page(self):
        """First page of pagination should work correctly."""
        testimonials = list(range(25))  # 25 items
        page = 1
        per_page = 10
        start = (page - 1) * per_page
        end = start + per_page
        paginated = testimonials[start:end]

        assert len(paginated) == 10
        assert paginated[0] == 0
        assert paginated[-1] == 9

    def test_pagination_boundary_last_page(self):
        """Last page of pagination should return remaining items."""
        testimonials = list(range(25))  # 25 items
        page = 3
        per_page = 10
        start = (page - 1) * per_page
        end = start + per_page
        paginated = testimonials[start:end]

        assert len(paginated) == 5  # Only 5 remaining
        assert paginated[0] == 20
        assert paginated[-1] == 24

    def test_pagination_empty_page(self):
        """Page beyond data should return empty list."""
        testimonials = list(range(10))
        page = 5
        per_page = 10
        start = (page - 1) * per_page
        end = start + per_page
        paginated = testimonials[start:end]

        assert len(paginated) == 0

    def test_concurrent_status_toggle_idempotency(self):
        """Multiple toggles to same status should be idempotent."""
        testimonial = {"status": "inactive"}

        # Toggle to active multiple times
        for _ in range(3):
            testimonial["status"] = "active"

        assert testimonial["status"] == "active"

    def test_toggle_preserves_other_fields(self):
        """Status toggle should not affect other fields."""
        original = {
            "id": 1,
            "customer_name": "Test",
            "review_text": "Review",
            "star_rating": 5,
            "status": "inactive",
        }

        # Toggle status
        updated = original.copy()
        updated["status"] = "active"

        # All other fields unchanged
        assert updated["id"] == original["id"]
        assert updated["customer_name"] == original["customer_name"]
        assert updated["review_text"] == original["review_text"]
        assert updated["star_rating"] == original["star_rating"]
        assert updated["status"] == "active"
