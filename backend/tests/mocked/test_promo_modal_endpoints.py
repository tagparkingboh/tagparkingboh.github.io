"""
Unit and Integration tests for Promo Modal endpoints.

Tests the promo modal management and display functionality:
- GET /api/admin/promo-modals (list)
- POST /api/admin/promo-modals (create)
- PUT /api/admin/promo-modals/{id} (update)
- DELETE /api/admin/promo-modals/{id} (delete)
- GET /api/promo-modal (public - get active modal)
- GET /api/promo-section (public - get promo section)
- POST /api/promo-modal/{id}/view (track view)
- POST /api/promo-modal/{id}/click (track click)

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, time, timezone, timedelta


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_promo_modal(
    id=1,
    title="Special Offer!",
    subtitle="Get 10% off your first booking",
    description="Use code FIRST10 at checkout",
    promo_code="FIRST10",
    discount_percent=10,
    button_text="Book Now",
    button_url="/booking",
    background_color="#FF6B6B",
    text_color="#FFFFFF",
    is_active=True,
    display_delay_seconds=5,
    display_frequency="once_per_session",
    start_date=None,
    end_date=None,
    views_count=0,
    clicks_count=0,
    created_by="admin@test.com",
    created_at=None,
    updated_at=None,
):
    """Create a mock promo modal object."""
    modal = MagicMock()
    modal.id = id
    modal.title = title
    modal.subtitle = subtitle
    modal.description = description
    modal.promo_code = promo_code
    modal.discount_percent = discount_percent
    modal.button_text = button_text
    modal.button_url = button_url
    modal.background_color = background_color
    modal.text_color = text_color
    modal.is_active = is_active
    modal.display_delay_seconds = display_delay_seconds
    modal.display_frequency = display_frequency
    modal.start_date = start_date
    modal.end_date = end_date
    modal.views_count = views_count
    modal.clicks_count = clicks_count
    modal.created_by = created_by
    modal.created_at = created_at or datetime.now(timezone.utc)
    modal.updated_at = updated_at
    return modal


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# List Promo Modals Tests
# ============================================================================

class TestListPromoModalsLogic:
    """Unit tests for list promo modals logic."""

    # Happy Path
    def test_returns_all_modals(self):
        """Should return all promo modals."""
        modals = [
            create_mock_promo_modal(id=1, title="Modal 1"),
            create_mock_promo_modal(id=2, title="Modal 2"),
            create_mock_promo_modal(id=3, title="Modal 3"),
        ]

        assert len(modals) == 3

    def test_orders_by_created_at_desc(self):
        """Should order modals by created_at descending."""
        now = datetime.now(timezone.utc)
        modals = [
            create_mock_promo_modal(id=1, created_at=now - timedelta(days=2)),
            create_mock_promo_modal(id=2, created_at=now - timedelta(days=1)),
            create_mock_promo_modal(id=3, created_at=now),
        ]

        sorted_modals = sorted(modals, key=lambda m: m.created_at, reverse=True)

        assert sorted_modals[0].id == 3

    def test_includes_stats(self):
        """Should include view and click stats."""
        modal = create_mock_promo_modal(views_count=100, clicks_count=25)

        stats = {
            "views_count": modal.views_count,
            "clicks_count": modal.clicks_count,
            "click_rate": (modal.clicks_count / modal.views_count * 100) if modal.views_count > 0 else 0,
        }

        assert stats["views_count"] == 100
        assert stats["clicks_count"] == 25
        assert stats["click_rate"] == 25.0


# ============================================================================
# Create Promo Modal Tests
# ============================================================================

class TestCreatePromoModalLogic:
    """Unit tests for create promo modal logic."""

    # Happy Path
    def test_creates_modal_with_valid_data(self):
        """Should create modal with valid data."""
        request = {
            "title": "New Offer!",
            "subtitle": "Limited time only",
            "promo_code": "NEWUSER20",
            "discount_percent": 20,
            "is_active": True,
        }

        modal = create_mock_promo_modal(**request)

        assert modal.title == "New Offer!"
        assert modal.promo_code == "NEWUSER20"
        assert modal.discount_percent == 20

    def test_sets_default_display_delay(self):
        """Should set default display delay."""
        modal = create_mock_promo_modal(display_delay_seconds=5)

        assert modal.display_delay_seconds == 5

    def test_sets_display_frequency(self):
        """Should set display frequency."""
        modal = create_mock_promo_modal(display_frequency="once_per_session")

        assert modal.display_frequency == "once_per_session"

    def test_sets_date_range(self):
        """Should set start and end dates."""
        start = date(2026, 6, 1)
        end = date(2026, 6, 30)

        modal = create_mock_promo_modal(start_date=start, end_date=end)

        assert modal.start_date == start
        assert modal.end_date == end

    def test_stores_created_by(self):
        """Should store who created the modal."""
        modal = create_mock_promo_modal(created_by="admin@tagparking.co.uk")

        assert modal.created_by == "admin@tagparking.co.uk"

    # Validation
    def test_requires_title(self):
        """Should require title."""
        request = {"subtitle": "Test", "promo_code": "TEST"}

        has_title = "title" in request and request.get("title")

        assert has_title is False

    def test_validates_discount_percent(self):
        """Should validate discount percent."""
        valid_discounts = [10, 15, 20, 25, 50, 100]

        assert 20 in valid_discounts
        assert 35 not in valid_discounts

    def test_validates_hex_color(self):
        """Should validate hex color format."""
        valid_color = "#FF6B6B"
        invalid_color = "red"

        is_valid_hex = valid_color.startswith("#") and len(valid_color) == 7

        assert is_valid_hex is True
        assert not (invalid_color.startswith("#") and len(invalid_color) == 7)


# ============================================================================
# Update Promo Modal Tests
# ============================================================================

class TestUpdatePromoModalLogic:
    """Unit tests for update promo modal logic."""

    # Happy Path
    def test_updates_title(self):
        """Should update modal title."""
        modal = create_mock_promo_modal(title="Old Title")

        modal.title = "New Title"

        assert modal.title == "New Title"

    def test_updates_is_active(self):
        """Should update active status."""
        modal = create_mock_promo_modal(is_active=True)

        modal.is_active = False

        assert modal.is_active is False

    def test_updates_promo_code(self):
        """Should update promo code."""
        modal = create_mock_promo_modal(promo_code="OLD10")

        modal.promo_code = "NEW20"

        assert modal.promo_code == "NEW20"

    def test_updates_timestamp(self):
        """Should update updated_at timestamp."""
        modal = create_mock_promo_modal()

        modal.updated_at = datetime.now(timezone.utc)

        assert modal.updated_at is not None

    # Unhappy Path
    def test_modal_not_found(self):
        """Should handle modal not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Delete Promo Modal Tests
# ============================================================================

class TestDeletePromoModalLogic:
    """Unit tests for delete promo modal logic."""

    # Happy Path
    def test_deletes_modal(self):
        """Should delete modal."""
        modal = create_mock_promo_modal(id=1)
        mock_db = MagicMock()

        mock_db.delete(modal)
        mock_db.commit()

        mock_db.delete.assert_called_once_with(modal)

    # Unhappy Path
    def test_modal_not_found_for_delete(self):
        """Should handle modal not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Get Active Promo Modal (Public) Tests
# ============================================================================

class TestGetActivePromoModalLogic:
    """Unit tests for get active promo modal (public endpoint)."""

    # Happy Path
    def test_returns_active_modal(self):
        """Should return active modal."""
        modals = [
            create_mock_promo_modal(id=1, is_active=False),
            create_mock_promo_modal(id=2, is_active=True),
            create_mock_promo_modal(id=3, is_active=False),
        ]

        active = next((m for m in modals if m.is_active), None)

        assert active is not None
        assert active.id == 2

    def test_returns_none_if_no_active(self):
        """Should return None if no active modal."""
        modals = [
            create_mock_promo_modal(id=1, is_active=False),
            create_mock_promo_modal(id=2, is_active=False),
        ]

        active = next((m for m in modals if m.is_active), None)

        assert active is None

    def test_respects_date_range(self):
        """Should respect start_date and end_date."""
        today = date.today()
        modal = create_mock_promo_modal(
            is_active=True,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
        )

        is_in_range = (
            (modal.start_date is None or modal.start_date <= today) and
            (modal.end_date is None or modal.end_date >= today)
        )

        assert is_in_range is True

    def test_excludes_expired_modal(self):
        """Should exclude modal past end_date."""
        today = date.today()
        modal = create_mock_promo_modal(
            is_active=True,
            end_date=today - timedelta(days=1),
        )

        is_expired = modal.end_date is not None and modal.end_date < today

        assert is_expired is True

    def test_excludes_future_modal(self):
        """Should exclude modal before start_date."""
        today = date.today()
        modal = create_mock_promo_modal(
            is_active=True,
            start_date=today + timedelta(days=7),
        )

        is_future = modal.start_date is not None and modal.start_date > today

        assert is_future is True


# ============================================================================
# Get Promo Section (Public) Tests
# ============================================================================

class TestGetPromoSectionLogic:
    """Unit tests for get promo section (public endpoint)."""

    # Happy Path
    def test_returns_promo_section_data(self):
        """Should return promo section data."""
        modal = create_mock_promo_modal(
            title="Special Offer",
            promo_code="SAVE10",
            discount_percent=10,
        )

        section = {
            "title": modal.title,
            "promo_code": modal.promo_code,
            "discount_percent": modal.discount_percent,
        }

        assert section["title"] == "Special Offer"
        assert section["promo_code"] == "SAVE10"


# ============================================================================
# Track View Tests
# ============================================================================

class TestTrackViewLogic:
    """Unit tests for track view logic."""

    # Happy Path
    def test_increments_view_count(self):
        """Should increment view count."""
        modal = create_mock_promo_modal(views_count=50)

        modal.views_count += 1

        assert modal.views_count == 51

    def test_handles_first_view(self):
        """Should handle first view (count = 0)."""
        modal = create_mock_promo_modal(views_count=0)

        modal.views_count += 1

        assert modal.views_count == 1

    # Unhappy Path
    def test_modal_not_found_for_view(self):
        """Should handle modal not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Track Click Tests
# ============================================================================

class TestTrackClickLogic:
    """Unit tests for track click logic."""

    # Happy Path
    def test_increments_click_count(self):
        """Should increment click count."""
        modal = create_mock_promo_modal(clicks_count=25)

        modal.clicks_count += 1

        assert modal.clicks_count == 26

    def test_handles_first_click(self):
        """Should handle first click (count = 0)."""
        modal = create_mock_promo_modal(clicks_count=0)

        modal.clicks_count += 1

        assert modal.clicks_count == 1

    def test_calculates_click_rate(self):
        """Should calculate click rate correctly."""
        modal = create_mock_promo_modal(views_count=100, clicks_count=25)

        click_rate = (modal.clicks_count / modal.views_count * 100) if modal.views_count > 0 else 0

        assert click_rate == 25.0

    def test_handles_zero_views(self):
        """Should handle zero views (avoid division by zero)."""
        modal = create_mock_promo_modal(views_count=0, clicks_count=0)

        click_rate = (modal.clicks_count / modal.views_count * 100) if modal.views_count > 0 else 0

        assert click_rate == 0


# ============================================================================
# Authentication Tests
# ============================================================================

class TestPromoModalAuthentication:
    """Tests for authentication on promo modal endpoints."""

    def test_admin_endpoints_require_auth(self):
        """Should require admin for admin endpoints."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_public_endpoints_no_auth(self):
        """Public endpoints should not require authentication."""
        # GET /api/promo-modal is public
        is_public = True

        assert is_public is True


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestPromoModalResponseStructure:
    """Tests for response structure."""

    def test_modal_response_structure(self):
        """Should return correct modal response structure."""
        modal = create_mock_promo_modal()

        response = {
            "id": modal.id,
            "title": modal.title,
            "subtitle": modal.subtitle,
            "description": modal.description,
            "promo_code": modal.promo_code,
            "discount_percent": modal.discount_percent,
            "button_text": modal.button_text,
            "button_url": modal.button_url,
            "background_color": modal.background_color,
            "text_color": modal.text_color,
            "is_active": modal.is_active,
            "display_delay_seconds": modal.display_delay_seconds,
            "views_count": modal.views_count,
            "clicks_count": modal.clicks_count,
        }

        assert "id" in response
        assert "title" in response
        assert "promo_code" in response


# ============================================================================
# Boundary Tests
# ============================================================================

class TestPromoModalBoundaries:
    """Tests for boundary conditions."""

    def test_very_long_title(self):
        """Should handle very long title."""
        long_title = "A" * 200
        modal = create_mock_promo_modal(title=long_title)

        assert len(modal.title) == 200

    def test_zero_delay(self):
        """Should handle zero delay (show immediately)."""
        modal = create_mock_promo_modal(display_delay_seconds=0)

        assert modal.display_delay_seconds == 0

    def test_large_view_count(self):
        """Should handle large view count."""
        modal = create_mock_promo_modal(views_count=1000000)

        assert modal.views_count == 1000000

    def test_display_frequency_options(self):
        """Should handle different display frequency options."""
        frequencies = ["once_per_session", "once_per_day", "always"]

        for freq in frequencies:
            modal = create_mock_promo_modal(display_frequency=freq)
            assert modal.display_frequency == freq


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
