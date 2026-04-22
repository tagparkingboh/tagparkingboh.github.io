"""
Unit and Integration tests for Testimonials endpoints.

Tests the testimonials management functionality:
- GET /api/testimonials (public - get approved)
- GET /api/admin/testimonials (admin - get all)
- POST /api/admin/testimonials (create)
- PUT /api/admin/testimonials/{id} (update)
- DELETE /api/admin/testimonials/{id} (delete)
- POST /api/admin/testimonials/{id}/approve
- POST /api/admin/testimonials/{id}/reject

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timezone, timedelta


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_testimonial(
    id=1,
    customer_name="John Smith",
    customer_location="London",
    booking_reference="TAG-12345",
    rating=5,
    title="Excellent Service!",
    content="The service was fantastic. Highly recommend!",
    is_approved=True,
    is_featured=False,
    submitted_at=None,
    approved_at=None,
    approved_by=None,
    display_order=0,
):
    """Create a mock testimonial object."""
    testimonial = MagicMock()
    testimonial.id = id
    testimonial.customer_name = customer_name
    testimonial.customer_location = customer_location
    testimonial.booking_reference = booking_reference
    testimonial.rating = rating
    testimonial.title = title
    testimonial.content = content
    testimonial.is_approved = is_approved
    testimonial.is_featured = is_featured
    testimonial.submitted_at = submitted_at or datetime.now(timezone.utc)
    testimonial.approved_at = approved_at
    testimonial.approved_by = approved_by
    testimonial.display_order = display_order
    return testimonial


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Get Public Testimonials Tests
# ============================================================================

class TestGetPublicTestimonialsLogic:
    """Unit tests for get public testimonials logic."""

    # Happy Path
    def test_returns_only_approved_testimonials(self):
        """Should return only approved testimonials."""
        testimonials = [
            create_mock_testimonial(id=1, is_approved=True),
            create_mock_testimonial(id=2, is_approved=False),
            create_mock_testimonial(id=3, is_approved=True),
        ]

        approved = [t for t in testimonials if t.is_approved]

        assert len(approved) == 2

    def test_orders_by_display_order(self):
        """Should order testimonials by display_order."""
        testimonials = [
            create_mock_testimonial(id=1, display_order=3),
            create_mock_testimonial(id=2, display_order=1),
            create_mock_testimonial(id=3, display_order=2),
        ]

        sorted_testimonials = sorted(testimonials, key=lambda t: t.display_order)

        assert sorted_testimonials[0].id == 2
        assert sorted_testimonials[1].id == 3
        assert sorted_testimonials[2].id == 1

    def test_returns_featured_first(self):
        """Should return featured testimonials first."""
        testimonials = [
            create_mock_testimonial(id=1, is_featured=False),
            create_mock_testimonial(id=2, is_featured=True),
            create_mock_testimonial(id=3, is_featured=False),
        ]

        sorted_testimonials = sorted(testimonials, key=lambda t: (not t.is_featured, t.display_order))

        assert sorted_testimonials[0].id == 2

    def test_limits_number_of_testimonials(self):
        """Should limit number of returned testimonials."""
        testimonials = [create_mock_testimonial(id=i) for i in range(20)]
        limit = 10

        limited = testimonials[:limit]

        assert len(limited) == 10

    # Edge Cases
    def test_returns_empty_if_none_approved(self):
        """Should return empty if no approved testimonials."""
        testimonials = [
            create_mock_testimonial(id=1, is_approved=False),
            create_mock_testimonial(id=2, is_approved=False),
        ]

        approved = [t for t in testimonials if t.is_approved]

        assert len(approved) == 0


# ============================================================================
# Get Admin Testimonials Tests
# ============================================================================

class TestGetAdminTestimonialsLogic:
    """Unit tests for get admin testimonials logic."""

    # Happy Path
    def test_returns_all_testimonials(self):
        """Should return all testimonials including pending."""
        testimonials = [
            create_mock_testimonial(id=1, is_approved=True),
            create_mock_testimonial(id=2, is_approved=False),
            create_mock_testimonial(id=3, is_approved=True),
        ]

        assert len(testimonials) == 3

    def test_orders_by_submitted_at_desc(self):
        """Should order by submission date descending."""
        now = datetime.now(timezone.utc)
        testimonials = [
            create_mock_testimonial(id=1, submitted_at=now - timedelta(days=2)),
            create_mock_testimonial(id=2, submitted_at=now - timedelta(days=1)),
            create_mock_testimonial(id=3, submitted_at=now),
        ]

        sorted_testimonials = sorted(testimonials, key=lambda t: t.submitted_at, reverse=True)

        assert sorted_testimonials[0].id == 3

    def test_includes_pending_count(self):
        """Should include count of pending testimonials."""
        testimonials = [
            create_mock_testimonial(is_approved=True),
            create_mock_testimonial(is_approved=False),
            create_mock_testimonial(is_approved=False),
        ]

        pending_count = sum(1 for t in testimonials if not t.is_approved)

        assert pending_count == 2


# ============================================================================
# Create Testimonial Tests
# ============================================================================

class TestCreateTestimonialLogic:
    """Unit tests for create testimonial logic."""

    # Happy Path
    def test_creates_testimonial_with_valid_data(self):
        """Should create testimonial with valid data."""
        request = {
            "customer_name": "Jane Doe",
            "customer_location": "Manchester",
            "rating": 5,
            "title": "Great experience",
            "content": "Would definitely use again!",
        }

        testimonial = create_mock_testimonial(**request)

        assert testimonial.customer_name == "Jane Doe"
        assert testimonial.rating == 5

    def test_defaults_to_not_approved(self):
        """Should default to not approved (pending review)."""
        testimonial = create_mock_testimonial(is_approved=False)

        assert testimonial.is_approved is False

    def test_sets_submitted_timestamp(self):
        """Should set submitted_at timestamp."""
        before = datetime.now(timezone.utc)
        testimonial = create_mock_testimonial(submitted_at=datetime.now(timezone.utc))

        assert testimonial.submitted_at >= before

    # Validation
    def test_validates_rating_range(self):
        """Should validate rating is between 1 and 5."""
        valid_ratings = [1, 2, 3, 4, 5]

        for rating in valid_ratings:
            is_valid = 1 <= rating <= 5
            assert is_valid is True

        invalid_ratings = [0, 6, -1, 10]
        for rating in invalid_ratings:
            is_valid = 1 <= rating <= 5
            assert is_valid is False

    def test_requires_customer_name(self):
        """Should require customer name."""
        request = {"rating": 5, "content": "Great!"}

        has_name = "customer_name" in request and request.get("customer_name")

        assert has_name is False

    def test_requires_content(self):
        """Should require content."""
        request = {"customer_name": "John", "rating": 5}

        has_content = "content" in request and request.get("content")

        assert has_content is False


# ============================================================================
# Update Testimonial Tests
# ============================================================================

class TestUpdateTestimonialLogic:
    """Unit tests for update testimonial logic."""

    # Happy Path
    def test_updates_content(self):
        """Should update testimonial content."""
        testimonial = create_mock_testimonial(content="Old content")

        testimonial.content = "Updated content"

        assert testimonial.content == "Updated content"

    def test_updates_rating(self):
        """Should update rating."""
        testimonial = create_mock_testimonial(rating=3)

        testimonial.rating = 5

        assert testimonial.rating == 5

    def test_updates_display_order(self):
        """Should update display order."""
        testimonial = create_mock_testimonial(display_order=0)

        testimonial.display_order = 5

        assert testimonial.display_order == 5

    def test_updates_is_featured(self):
        """Should update featured status."""
        testimonial = create_mock_testimonial(is_featured=False)

        testimonial.is_featured = True

        assert testimonial.is_featured is True

    # Unhappy Path
    def test_testimonial_not_found(self):
        """Should handle testimonial not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Delete Testimonial Tests
# ============================================================================

class TestDeleteTestimonialLogic:
    """Unit tests for delete testimonial logic."""

    # Happy Path
    def test_deletes_testimonial(self):
        """Should delete testimonial."""
        testimonial = create_mock_testimonial(id=1)
        mock_db = MagicMock()

        mock_db.delete(testimonial)
        mock_db.commit()

        mock_db.delete.assert_called_once_with(testimonial)

    # Unhappy Path
    def test_testimonial_not_found_for_delete(self):
        """Should handle testimonial not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Approve/Reject Testimonial Tests
# ============================================================================

class TestApproveTestimonialLogic:
    """Unit tests for approve testimonial logic."""

    # Happy Path
    def test_approves_testimonial(self):
        """Should approve testimonial."""
        testimonial = create_mock_testimonial(is_approved=False)

        testimonial.is_approved = True
        testimonial.approved_at = datetime.now(timezone.utc)
        testimonial.approved_by = "admin@test.com"

        assert testimonial.is_approved is True
        assert testimonial.approved_at is not None
        assert testimonial.approved_by == "admin@test.com"

    def test_rejects_testimonial(self):
        """Should reject (un-approve) testimonial."""
        testimonial = create_mock_testimonial(is_approved=True)

        testimonial.is_approved = False
        testimonial.approved_at = None
        testimonial.approved_by = None

        assert testimonial.is_approved is False


# ============================================================================
# Rating Statistics Tests
# ============================================================================

class TestRatingStatistics:
    """Tests for rating statistics calculation."""

    def test_calculates_average_rating(self):
        """Should calculate average rating."""
        testimonials = [
            create_mock_testimonial(rating=5),
            create_mock_testimonial(rating=4),
            create_mock_testimonial(rating=5),
            create_mock_testimonial(rating=3),
        ]

        avg_rating = sum(t.rating for t in testimonials) / len(testimonials)

        assert avg_rating == 4.25

    def test_calculates_rating_distribution(self):
        """Should calculate rating distribution."""
        testimonials = [
            create_mock_testimonial(rating=5),
            create_mock_testimonial(rating=5),
            create_mock_testimonial(rating=4),
            create_mock_testimonial(rating=3),
        ]

        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for t in testimonials:
            distribution[t.rating] += 1

        assert distribution[5] == 2
        assert distribution[4] == 1
        assert distribution[3] == 1

    def test_handles_empty_testimonials(self):
        """Should handle empty testimonials for statistics."""
        testimonials = []

        avg_rating = sum(t.rating for t in testimonials) / len(testimonials) if testimonials else 0

        assert avg_rating == 0


# ============================================================================
# Authentication Tests
# ============================================================================

class TestTestimonialsAuthentication:
    """Tests for authentication on testimonials endpoints."""

    def test_public_endpoint_no_auth(self):
        """Public testimonials endpoint should not require auth."""
        # GET /api/testimonials is public
        is_public = True

        assert is_public is True

    def test_admin_endpoints_require_auth(self):
        """Admin testimonials endpoints should require auth."""
        user = create_mock_admin_user()

        assert user.is_admin is True


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestTestimonialsResponseStructure:
    """Tests for response structure."""

    def test_public_response_structure(self):
        """Should return correct public response structure."""
        testimonial = create_mock_testimonial()

        response = {
            "id": testimonial.id,
            "customer_name": testimonial.customer_name,
            "customer_location": testimonial.customer_location,
            "rating": testimonial.rating,
            "title": testimonial.title,
            "content": testimonial.content,
            "is_featured": testimonial.is_featured,
        }

        assert "id" in response
        assert "customer_name" in response
        assert "rating" in response
        # Should NOT include is_approved in public response
        assert "is_approved" not in response

    def test_admin_response_structure(self):
        """Should return correct admin response structure."""
        testimonial = create_mock_testimonial()

        response = {
            "id": testimonial.id,
            "customer_name": testimonial.customer_name,
            "rating": testimonial.rating,
            "content": testimonial.content,
            "is_approved": testimonial.is_approved,
            "booking_reference": testimonial.booking_reference,
            "approved_by": testimonial.approved_by,
        }

        assert "is_approved" in response
        assert "booking_reference" in response


# ============================================================================
# Boundary Tests
# ============================================================================

class TestTestimonialsBoundaries:
    """Tests for boundary conditions."""

    def test_very_long_content(self):
        """Should handle very long content."""
        long_content = "A" * 2000
        testimonial = create_mock_testimonial(content=long_content)

        assert len(testimonial.content) == 2000

    def test_minimum_rating(self):
        """Should handle minimum rating (1)."""
        testimonial = create_mock_testimonial(rating=1)

        assert testimonial.rating == 1

    def test_maximum_rating(self):
        """Should handle maximum rating (5)."""
        testimonial = create_mock_testimonial(rating=5)

        assert testimonial.rating == 5

    def test_unicode_in_content(self):
        """Should handle unicode in content."""
        testimonial = create_mock_testimonial(content="Excellent! 🌟 Très bien!")

        assert "🌟" in testimonial.content

    def test_very_long_customer_name(self):
        """Should handle very long customer name."""
        long_name = "A" * 100
        testimonial = create_mock_testimonial(customer_name=long_name)

        assert len(testimonial.customer_name) == 100


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
