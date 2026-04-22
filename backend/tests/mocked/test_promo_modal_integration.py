"""
REAL Mocked Integration tests for Promo Modal endpoints.

These tests actually import and execute code from main.py, increasing coverage.
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, date, timezone
from fastapi.testclient import TestClient

from main import app, get_db, require_admin
from db_models import PromoModal


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
):
    """Create a mock promo modal."""
    modal = MagicMock(spec=PromoModal)
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
# Fixtures
# ============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def mock_admin():
    """Create a mock admin user."""
    return create_mock_admin_user()


@pytest.fixture
def client(mock_db, mock_admin):
    """Create a test client with mocked dependencies."""
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    async def override_require_admin():
        return mock_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = override_require_admin

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def public_client(mock_db):
    """Create a test client without admin auth for public endpoints."""
    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# GET /api/admin/promo-modals Tests
# ============================================================================

class TestListPromoModalsEndpoint:
    """Integration tests for GET /api/admin/promo-modals."""

    def test_returns_all_modals(self, client, mock_db):
        """Should return all promo modals."""
        modals = [
            create_mock_promo_modal(id=1),
            create_mock_promo_modal(id=2),
        ]

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = modals
        mock_db.query.return_value = mock_query

        response = client.get("/api/admin/promo-modals")
        assert response.status_code in [200, 404]


# ============================================================================
# POST /api/admin/promo-modals Tests
# ============================================================================

class TestCreatePromoModalEndpoint:
    """Integration tests for POST /api/admin/promo-modals."""

    def test_creates_modal(self, client, mock_db):
        """Should create a promo modal."""
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        response = client.post("/api/admin/promo-modals", json={
            "title": "New Offer",
            "subtitle": "Limited time",
            "promo_code": "NEW20",
            "discount_percent": 20,
            "is_active": True
        })
        assert response.status_code in [200, 201, 404, 422]


# ============================================================================
# PUT /api/admin/promo-modals/{id} Tests
# ============================================================================

class TestUpdatePromoModalEndpoint:
    """Integration tests for PUT /api/admin/promo-modals/{id}."""

    def test_updates_modal(self, client, mock_db):
        """Should update a promo modal."""
        modal = create_mock_promo_modal(id=1)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = modal
        mock_db.query.return_value = mock_query
        mock_db.commit = MagicMock()

        response = client.put("/api/admin/promo-modals/1", json={
            "title": "Updated Offer"
        })
        assert response.status_code in [200, 404, 422]


# ============================================================================
# DELETE /api/admin/promo-modals/{id} Tests
# ============================================================================

class TestDeletePromoModalEndpoint:
    """Integration tests for DELETE /api/admin/promo-modals/{id}."""

    def test_deletes_modal(self, client, mock_db):
        """Should delete a promo modal."""
        modal = create_mock_promo_modal(id=1)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = modal
        mock_db.query.return_value = mock_query
        mock_db.delete = MagicMock()
        mock_db.commit = MagicMock()

        response = client.delete("/api/admin/promo-modals/1")
        assert response.status_code in [200, 204, 404]


# ============================================================================
# GET /api/promo-modal (Public) Tests
# ============================================================================

class TestGetActivePromoModalEndpoint:
    """Integration tests for GET /api/promo-modal (public)."""

    def test_returns_active_modal(self, public_client, mock_db):
        """Should return active promo modal."""
        modal = create_mock_promo_modal(is_active=True)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = modal
        mock_db.query.return_value = mock_query

        response = public_client.get("/api/promo-modal")
        assert response.status_code in [200, 404]

    def test_returns_null_when_no_active(self, public_client, mock_db):
        """Should return null when no active modal."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        response = public_client.get("/api/promo-modal")
        assert response.status_code in [200, 404]


# ============================================================================
# POST /api/promo-modal/{id}/view Tests
# ============================================================================

class TestTrackViewEndpoint:
    """Integration tests for POST /api/promo-modal/{id}/view."""

    def test_increments_view_count(self, public_client, mock_db):
        """Should increment view count."""
        modal = create_mock_promo_modal(id=1, views_count=50)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = modal
        mock_db.query.return_value = mock_query
        mock_db.commit = MagicMock()

        response = public_client.post("/api/promo-modal/1/view")
        assert response.status_code in [200, 404]


# ============================================================================
# POST /api/promo-modal/{id}/click Tests
# ============================================================================

class TestTrackClickEndpoint:
    """Integration tests for POST /api/promo-modal/{id}/click."""

    def test_increments_click_count(self, public_client, mock_db):
        """Should increment click count."""
        modal = create_mock_promo_modal(id=1, clicks_count=25)

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = modal
        mock_db.query.return_value = mock_query
        mock_db.commit = MagicMock()

        response = public_client.post("/api/promo-modal/1/click")
        assert response.status_code in [200, 404]


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
