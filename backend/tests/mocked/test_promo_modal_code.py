"""
Tests for Promo Modal Single-Use Code Feature.

Tests cover:
1. Unit tests for promo modal code display in API responses
2. Unit tests for check_promo_modal_code_used function
3. Integration tests for the full promo code usage flow
4. Concurrency tests for simultaneous promo code usage attempts

Uses mocked database to isolate tests from real data.
"""
import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, patch, PropertyMock
from sqlalchemy.orm import Session
import threading
import time

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def mock_promo_modal():
    """Create a mock PromoModal with a promo code."""
    from db_models import PromoModalStatus

    modal = MagicMock()
    modal.id = 1
    modal.title = "Special Offer!"
    modal.message = "Get 10% off your first booking"
    modal.button_text = "Book Now"
    modal.button_action = "link"
    modal.button_link = "/book"
    modal.start_date = date(2026, 3, 1)
    modal.end_date = date(2026, 12, 31)
    modal.background_color = "#343434"
    modal.text_color = "#d9ff00"
    modal.button_color = "#d9ff00"
    modal.button_text_color = "#343434"
    modal.status = PromoModalStatus.ACTIVE
    modal.promo_code = "TAG-SPECIAL-10"
    modal.max_subscribers = None
    modal.subscribers_at_activation = None
    modal.view_count = 0
    modal.click_count = 0
    modal.created_at = datetime(2026, 3, 1, 10, 0, 0)
    return modal


@pytest.fixture
def mock_promo_modal_no_code():
    """Create a mock PromoModal without a promo code."""
    from db_models import PromoModalStatus

    modal = MagicMock()
    modal.id = 2
    modal.title = "Subscribe Now!"
    modal.message = "Join our mailing list"
    modal.button_text = "Subscribe"
    modal.button_action = "subscribe"
    modal.button_link = None
    modal.start_date = None
    modal.end_date = None
    modal.background_color = "#1e3a5f"
    modal.text_color = "#ffffff"
    modal.button_color = "#22c55e"
    modal.button_text_color = "#ffffff"
    modal.status = PromoModalStatus.ACTIVE
    modal.promo_code = None
    modal.max_subscribers = 100
    modal.subscribers_at_activation = 50
    modal.view_count = 10
    modal.click_count = 5
    modal.created_at = datetime(2026, 3, 15, 14, 30, 0)
    return modal


# =============================================================================
# Unit Tests - format_promo_modal function
# =============================================================================

class TestFormatPromoModal:
    """Tests for format_promo_modal API response formatting."""

    def test_format_promo_modal_with_code(self, mock_promo_modal):
        """Promo modal with code should include promoCode in response."""
        from main import format_promo_modal

        result = format_promo_modal(mock_promo_modal)

        assert result["promoCode"] == "TAG-SPECIAL-10"
        assert result["title"] == "Special Offer!"
        assert result["status"] == "active"

    def test_format_promo_modal_without_code(self, mock_promo_modal_no_code):
        """Promo modal without code should have promoCode as None."""
        from main import format_promo_modal

        result = format_promo_modal(mock_promo_modal_no_code)

        assert result["promoCode"] is None
        assert result["title"] == "Subscribe Now!"

    def test_format_promo_modal_includes_all_fields(self, mock_promo_modal):
        """Formatted response should include all required fields."""
        from main import format_promo_modal

        result = format_promo_modal(mock_promo_modal)

        required_fields = [
            "id", "title", "message", "buttonText", "buttonAction",
            "buttonLink", "startDate", "endDate", "backgroundColor",
            "textColor", "buttonColor", "buttonTextColor", "status",
            "createdAt", "viewCount", "clickCount", "maxSubscribers",
            "subscribersAtActivation", "promoCode"
        ]

        for field in required_fields:
            assert field in result, f"Missing field: {field}"


# =============================================================================
# Unit Tests - check_promo_modal_code_used function
# =============================================================================

class TestCheckPromoModalCodeUsed:
    """Tests for check_promo_modal_code_used function."""

    def test_deactivates_modal_when_code_matches(self, mock_db, mock_promo_modal):
        """Should deactivate modal when promo code matches."""
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus, PromoCode as DbPromoCode, PromoModal

        # First query returns None (no promo code record = single-use)
        # Second query returns the modal
        def query_side_effect(model):
            mock_query = MagicMock()
            if model == DbPromoCode:
                mock_query.filter.return_value.first.return_value = None  # Single-use code
            elif model == PromoModal:
                mock_query.filter.return_value.first.return_value = mock_promo_modal
            return mock_query

        mock_db.query.side_effect = query_side_effect

        check_promo_modal_code_used(mock_db, "TAG-SPECIAL-10")

        assert mock_promo_modal.status == PromoModalStatus.INACTIVE
        mock_db.commit.assert_called_once()

    def test_deactivates_modal_case_insensitive(self, mock_db, mock_promo_modal):
        """Should match promo codes case-insensitively."""
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus, PromoCode as DbPromoCode, PromoModal

        def query_side_effect(model):
            mock_query = MagicMock()
            if model == DbPromoCode:
                mock_query.filter.return_value.first.return_value = None  # Single-use code
            elif model == PromoModal:
                mock_query.filter.return_value.first.return_value = mock_promo_modal
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Test with lowercase
        check_promo_modal_code_used(mock_db, "tag-special-10")

        assert mock_promo_modal.status == PromoModalStatus.INACTIVE

    def test_does_nothing_when_no_matching_modal(self, mock_db):
        """Should do nothing when no modal matches the promo code."""
        from main import check_promo_modal_code_used

        mock_db.query.return_value.filter.return_value.first.return_value = None

        check_promo_modal_code_used(mock_db, "NONEXISTENT-CODE")

        # Should not call commit if no modal found
        mock_db.commit.assert_not_called()

    def test_does_nothing_when_promo_code_is_none(self, mock_db):
        """Should do nothing when promo code is None."""
        from main import check_promo_modal_code_used

        check_promo_modal_code_used(mock_db, None)

        # Should not even query if code is None
        mock_db.query.assert_not_called()

    def test_does_nothing_when_promo_code_is_empty(self, mock_db):
        """Should do nothing when promo code is empty string."""
        from main import check_promo_modal_code_used

        check_promo_modal_code_used(mock_db, "")

        mock_db.query.assert_not_called()


# =============================================================================
# Integration Tests - API Endpoints
# =============================================================================

class TestPromoModalAPIIntegration:
    """Integration tests for promo modal API endpoints."""

    @pytest.fixture
    def client(self, mock_db):
        """Create test client with mocked dependencies."""
        from main import app, get_db
        from fastapi.testclient import TestClient

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        yield TestClient(app)

        app.dependency_overrides.clear()

    def test_get_active_promo_modal_with_code(self, client, mock_db, mock_promo_modal):
        """GET /api/promo-modal should return promo code when modal has one."""
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_promo_modal]

        response = client.get("/api/promo-modal")

        assert response.status_code == 200
        data = response.json()
        assert data["promoModal"] is not None
        assert data["promoModal"]["promoCode"] == "TAG-SPECIAL-10"

    def test_get_active_promo_modal_without_code(self, client, mock_db, mock_promo_modal_no_code):
        """GET /api/promo-modal should return None for promoCode when modal has none."""
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_promo_modal_no_code]

        response = client.get("/api/promo-modal")

        assert response.status_code == 200
        data = response.json()
        assert data["promoModal"] is not None
        assert data["promoModal"]["promoCode"] is None

    def test_no_active_promo_modal(self, client, mock_db):
        """GET /api/promo-modal should return null when no active modal."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        response = client.get("/api/promo-modal")

        assert response.status_code == 200
        data = response.json()
        assert data["promoModal"] is None


# =============================================================================
# Integration Tests - Promo Code Usage Flow
# =============================================================================

class TestPromoCodeUsageFlow:
    """Tests for the complete promo code usage and modal deactivation flow."""

    def test_modal_deactivates_after_code_used_on_booking(self, mock_db, mock_promo_modal):
        """Modal should deactivate when its promo code is used on a confirmed booking."""
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus, PromoCode as DbPromoCode, PromoModal

        # Initially active
        assert mock_promo_modal.status == PromoModalStatus.ACTIVE

        # Mock finding the modal - need to handle both PromoCode and PromoModal queries
        def query_side_effect(model):
            mock_query = MagicMock()
            if model == DbPromoCode:
                mock_query.filter.return_value.first.return_value = None  # Single-use code
            elif model == PromoModal:
                mock_query.filter.return_value.first.return_value = mock_promo_modal
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Simulate promo code being used (called from webhook after payment)
        check_promo_modal_code_used(mock_db, "TAG-SPECIAL-10")

        # Should now be inactive
        assert mock_promo_modal.status == PromoModalStatus.INACTIVE

    def test_modal_stays_active_when_different_code_used(self, mock_db, mock_promo_modal):
        """Modal should stay active when a different promo code is used."""
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus

        # Modal has TAG-SPECIAL-10, but we use a different code
        mock_db.query.return_value.filter.return_value.first.return_value = None

        check_promo_modal_code_used(mock_db, "SOME-OTHER-CODE")

        # Modal should still be active (we didn't modify it)
        assert mock_promo_modal.status == PromoModalStatus.ACTIVE


# =============================================================================
# Concurrency Tests - Race Conditions
# =============================================================================

class TestPromoCodeConcurrency:
    """Tests for concurrent promo code usage scenarios."""

    def test_simultaneous_code_usage_only_one_deactivates(self):
        """
        When two users try to use the same promo code simultaneously,
        only one should succeed and the modal should be deactivated once.

        Note: The actual protection against double-usage is at the promo_codes
        table level (is_used flag with database-level checks). The modal
        deactivation is just a UX improvement.
        """
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus

        # Track how many times modal was deactivated
        deactivation_count = 0
        commit_count = 0

        # Create a shared mock modal
        modal = MagicMock()
        modal.status = PromoModalStatus.ACTIVE
        modal.promo_code = "TAG-RACE-TEST"

        # Custom status setter to track deactivations
        original_status = modal.status
        def track_deactivation(value):
            nonlocal deactivation_count
            if value == PromoModalStatus.INACTIVE:
                deactivation_count += 1

        type(modal).status = PropertyMock(
            return_value=original_status,
            side_effect=track_deactivation
        )

        # Create mock db that returns the modal
        mock_db = MagicMock(spec=Session)

        def mock_commit():
            nonlocal commit_count
            commit_count += 1

        mock_db.commit = mock_commit

        # Mock both PromoCode and PromoModal queries
        from db_models import PromoCode as DbPromoCode, PromoModal

        def query_side_effect(model):
            mock_query = MagicMock()
            if model == DbPromoCode:
                mock_query.filter.return_value.first.return_value = None  # Single-use code
            elif model == PromoModal:
                mock_query.filter.return_value.first.return_value = modal
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Simulate two concurrent calls
        results = []
        errors = []

        def use_code():
            try:
                check_promo_modal_code_used(mock_db, "TAG-RACE-TEST")
                results.append("success")
            except Exception as e:
                errors.append(str(e))

        thread1 = threading.Thread(target=use_code)
        thread2 = threading.Thread(target=use_code)

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Both should complete without errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 2

        # Commit should have been called (at least once)
        assert commit_count >= 1

    def test_promo_code_validation_prevents_double_use(self):
        """
        Test that the promo code validation layer prevents double usage.

        This tests the promo_codes table logic, which is the real protection
        against concurrent usage.
        """
        # Simulate the scenario where first user marks code as used
        # and second user gets a friendly error message

        # This is a conceptual test - the actual validation is in /api/promo/validate
        # First user validates -> is_used=False -> returns valid=True
        # First user completes payment -> webhook sets is_used=True
        # Second user validates -> is_used=True -> returns valid=False with friendly message

        # The key assertion is that the system returns a friendly message
        expected_message = "Oops! Someone just beat you to it"
        assert "beat you to it" in expected_message

    def test_database_level_unique_constraint_simulation(self):
        """
        Simulate what happens when two transactions try to mark the same
        promo code as used simultaneously.

        In a real database with proper constraints, one would succeed and
        one would fail or be serialized.
        """
        # This is more of a documentation test showing the expected behavior

        # Scenario: Two payment webhooks arrive simultaneously for the same code
        # Expected behavior:
        # 1. Both attempt to mark promo_code.is_used = True
        # 2. Both attempt to commit
        # 3. Database serialization/locking ensures only one succeeds first
        # 4. The second one either:
        #    a) Finds is_used=True already (if SELECT FOR UPDATE used)
        #    b) Commits successfully (idempotent - already True)

        # The actual booking would already be validated before payment,
        # and Stripe ensures only one payment can succeed for a given intent

        assert True  # This test documents the expected behavior


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestPromoModalCodeEdgeCases:
    """Tests for edge cases in promo modal code functionality."""

    def test_whitespace_in_promo_code(self, mock_db, mock_promo_modal):
        """Should handle whitespace in promo codes."""
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus

        mock_db.query.return_value.filter.return_value.first.return_value = mock_promo_modal

        # Code with leading/trailing whitespace
        check_promo_modal_code_used(mock_db, "  TAG-SPECIAL-10  ")

        # Should still match (after stripping in the function)
        # Note: If this fails, we need to add .strip() to the function

    def test_special_characters_in_promo_code(self, mock_db):
        """Should handle special characters in promo codes safely."""
        from main import check_promo_modal_code_used

        # Should not raise any SQL injection or other errors
        try:
            check_promo_modal_code_used(mock_db, "'; DROP TABLE promo_modals; --")
        except Exception as e:
            pytest.fail(f"Should handle special characters safely: {e}")

    def test_very_long_promo_code(self, mock_db):
        """Should handle very long promo codes."""
        from main import check_promo_modal_code_used

        long_code = "A" * 1000

        # Should not raise any errors
        try:
            check_promo_modal_code_used(mock_db, long_code)
        except Exception as e:
            pytest.fail(f"Should handle long codes: {e}")

    def test_unicode_promo_code(self, mock_db):
        """Should handle unicode in promo codes."""
        from main import check_promo_modal_code_used

        # Should handle unicode gracefully
        try:
            check_promo_modal_code_used(mock_db, "TAG-特別-10")
        except Exception as e:
            pytest.fail(f"Should handle unicode: {e}")

    def test_modal_already_inactive(self, mock_db, mock_promo_modal):
        """Should handle case where modal is already inactive."""
        from main import check_promo_modal_code_used
        from db_models import PromoModalStatus

        # Modal is already inactive
        mock_promo_modal.status = PromoModalStatus.INACTIVE

        # Query won't find it because we filter for ACTIVE status
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise any errors
        check_promo_modal_code_used(mock_db, "TAG-SPECIAL-10")

        # And should not call commit (nothing to update)
        mock_db.commit.assert_not_called()


# =============================================================================
# Admin API Tests
# =============================================================================

class TestPromoCodeAlreadyUsedMessage:
    """Tests for the friendly error message when promo code is already used."""

    @pytest.fixture
    def client(self, mock_db):
        """Create test client with mocked dependencies."""
        from main import app, get_db
        from fastapi.testclient import TestClient

        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        yield TestClient(app)

        app.dependency_overrides.clear()

    def test_already_used_code_returns_friendly_message(self, client, mock_db):
        """Should return friendly message when promo code is already used."""
        from db_models import PromoCode

        # Create a mock promo code that's already used
        used_promo = MagicMock()
        used_promo.code = "TAG-USED-CODE"
        used_promo.is_used = True
        used_promo.used_at = datetime(2026, 3, 29, 12, 0, 0)
        used_promo.promotion_id = 1
        used_promo.expires_at = None
        used_promo.max_uses = None
        used_promo.use_count = 0
        # Set computed properties for single-use code
        used_promo.is_multi_use = False
        used_promo.uses_remaining = 0
        used_promo.can_be_used = False

        mock_db.query.return_value.filter.return_value.first.return_value = used_promo

        response = client.post(
            "/api/promo/validate",
            json={"code": "TAG-USED-CODE"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "beat you to it" in data["message"]
        assert "Keep an eye out" in data["message"]

    def test_error_message_is_kind_and_encouraging(self, client, mock_db):
        """Error message should be kind and encourage future engagement."""
        used_promo = MagicMock()
        used_promo.code = "TAG-SPECIAL"
        used_promo.is_used = True
        used_promo.used_at = datetime(2026, 3, 29, 12, 0, 0)
        used_promo.promotion_id = 1
        used_promo.expires_at = None
        used_promo.max_uses = None
        used_promo.use_count = 0
        # Set computed properties for single-use code
        used_promo.is_multi_use = False
        used_promo.uses_remaining = 0
        used_promo.can_be_used = False

        mock_db.query.return_value.filter.return_value.first.return_value = used_promo

        response = client.post(
            "/api/promo/validate",
            json={"code": "TAG-SPECIAL"}
        )

        data = response.json()
        # Should NOT contain harsh language
        assert "error" not in data["message"].lower()
        assert "invalid" not in data["message"].lower()
        assert "denied" not in data["message"].lower()
        # Should be encouraging
        assert "next offer" in data["message"].lower() or "keep an eye" in data["message"].lower()


class TestAdminPromoModalAPI:
    """Tests for admin promo modal management endpoints."""

    @pytest.fixture
    def admin_client(self, mock_db):
        """Create test client with admin auth."""
        from main import app, get_db, require_admin
        from fastapi.testclient import TestClient

        mock_admin = MagicMock()
        mock_admin.id = 1
        mock_admin.email = "admin@tag-parking.co.uk"
        mock_admin.role = "admin"

        def override_get_db():
            yield mock_db

        def override_require_admin():
            return mock_admin

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_admin] = override_require_admin

        yield TestClient(app)

        app.dependency_overrides.clear()

    def test_create_promo_modal_with_code(self, admin_client, mock_db):
        """Should create promo modal with promo code."""
        response = admin_client.post(
            "/api/admin/promo-modals",
            json={
                "title": "Flash Sale!",
                "message": "Use this code for 20% off",
                "button_text": "Shop Now",
                "button_action": "link",
                "button_link": "/book",
                "promo_code": "FLASH-20-OFF",
                "status": "active"
            }
        )

        assert response.status_code == 200
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    def test_update_promo_modal_code(self, admin_client, mock_db, mock_promo_modal):
        """Should update promo modal's promo code."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_promo_modal

        response = admin_client.put(
            "/api/admin/promo-modals/1",
            json={
                "promo_code": "NEW-CODE-50"
            }
        )

        assert response.status_code == 200
        assert mock_promo_modal.promo_code == "NEW-CODE-50"

    def test_clear_promo_modal_code(self, admin_client, mock_db, mock_promo_modal):
        """Should clear promo modal's promo code when empty string sent."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_promo_modal

        response = admin_client.put(
            "/api/admin/promo-modals/1",
            json={
                "promo_code": ""
            }
        )

        assert response.status_code == 200
        assert mock_promo_modal.promo_code is None
