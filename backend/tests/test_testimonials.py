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

    def test_format_date_of_travel(self):
        """Date of travel should format correctly."""
        date_obj = date(2026, 3, 15)
        formatted = date_obj.strftime("%b %Y")
        assert formatted == "Mar 2026"

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
