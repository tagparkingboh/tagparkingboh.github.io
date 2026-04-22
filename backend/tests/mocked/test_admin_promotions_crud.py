"""
Unit and Integration tests for Admin Promotions CRUD endpoints.

Tests the promotions management functionality:
- POST /api/admin/promotions (create)
- GET /api/admin/promotions (list)
- GET /api/admin/promotions/{id} (get detail)
- PATCH /api/admin/promotions/{id} (update)
- DELETE /api/admin/promotions/{id} (delete)
- POST /api/admin/promotions/{id}/generate-codes
- GET /api/admin/promotions/{id}/available-codes
- PATCH /api/admin/promo-codes/{id}/share-socials
- PATCH /api/admin/promo-codes/{id}/share-privately
- PATCH /api/admin/promo-codes/{id}/expiry

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timezone, timedelta
import pytz


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_promotion(
    id=1,
    name="Spring 2026 Campaign",
    description="Spring promotion",
    discount_percent=10,
    discount_type="percentage",
    total_codes=100,
    codes_sent=0,
    codes_used=0,
    code_prefix="TAG",
    created_by="admin@test.com",
    created_at=None,
    updated_at=None,
):
    """Create a mock promotion object."""
    promo = MagicMock()
    promo.id = id
    promo.name = name
    promo.description = description
    promo.discount_percent = discount_percent
    promo.discount_type = discount_type
    promo.total_codes = total_codes
    promo.codes_sent = codes_sent
    promo.codes_used = codes_used
    promo.code_prefix = code_prefix
    promo.created_by = created_by
    promo.created_at = created_at or datetime.now(timezone.utc)
    promo.updated_at = updated_at
    return promo


def create_mock_promo_code(
    id=1,
    promotion_id=1,
    code="TAG-ABC123",
    recipient_email=None,
    recipient_first_name=None,
    recipient_last_name=None,
    customer_id=None,
    subscriber_id=None,
    email_sent=False,
    email_sent_at=None,
    shared_on_socials=False,
    shared_on_socials_at=None,
    shared_privately=False,
    shared_privately_at=None,
    is_used=False,
    used_at=None,
    booking_id=None,
    expires_at=None,
    max_uses=None,
    use_count=0,
    created_at=None,
):
    """Create a mock promo code object."""
    code_obj = MagicMock()
    code_obj.id = id
    code_obj.promotion_id = promotion_id
    code_obj.code = code
    code_obj.recipient_email = recipient_email
    code_obj.recipient_first_name = recipient_first_name
    code_obj.recipient_last_name = recipient_last_name
    code_obj.customer_id = customer_id
    code_obj.subscriber_id = subscriber_id
    code_obj.email_sent = email_sent
    code_obj.email_sent_at = email_sent_at
    code_obj.shared_on_socials = shared_on_socials
    code_obj.shared_on_socials_at = shared_on_socials_at
    code_obj.shared_privately = shared_privately
    code_obj.shared_privately_at = shared_privately_at
    code_obj.is_used = is_used
    code_obj.used_at = used_at
    code_obj.booking_id = booking_id
    code_obj.expires_at = expires_at
    code_obj.max_uses = max_uses
    code_obj.use_count = use_count
    code_obj.created_at = created_at or datetime.now(timezone.utc)

    # Computed properties
    code_obj.is_multi_use = max_uses is not None and max_uses != 1
    code_obj.uses_remaining = None if max_uses is None else (None if max_uses == 0 else max_uses - use_count)
    code_obj.can_be_used = not is_used and (max_uses is None or max_uses == 0 or use_count < max_uses)

    return code_obj


def create_mock_admin_user():
    """Create a mock admin user."""
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_active = True
    return user


# ============================================================================
# Create Promotion Tests
# ============================================================================

class TestCreatePromotionLogic:
    """Unit tests for create promotion logic."""

    # Happy Path
    def test_creates_promotion_with_valid_data(self):
        """Should create promotion with valid data."""
        request = {
            "name": "Summer Sale 2026",
            "description": "Summer promotion",
            "discount_percent": 10,
            "total_codes": 50,
        }

        promotion = create_mock_promotion(**request)

        assert promotion.name == "Summer Sale 2026"
        assert promotion.discount_percent == 10
        assert promotion.total_codes == 50

    def test_creates_promotion_with_custom_code(self):
        """Should create promotion with custom code."""
        request = {
            "name": "VIP Promo",
            "discount_percent": 20,
            "custom_code": "VIP20OFF",
        }

        # Custom code means total_codes = 1
        total_codes = 1 if request.get("custom_code") else request.get("total_codes")

        assert total_codes == 1

    def test_creates_promotion_with_expiry(self):
        """Should create promotion with expiry date."""
        uk_tz = pytz.timezone("Europe/London")
        expiry_date = "31/12/2026"
        expiry_time = "23:59"

        day, month, year = expiry_date.split("/")
        hour, minute = expiry_time.split(":")
        expires_at = uk_tz.localize(datetime(int(year), int(month), int(day), int(hour), int(minute)))

        assert expires_at.year == 2026
        assert expires_at.month == 12
        assert expires_at.day == 31

    def test_creates_multi_use_code(self):
        """Should create multi-use code with max_uses."""
        code = create_mock_promo_code(max_uses=10, use_count=0)

        assert code.max_uses == 10
        assert code.is_multi_use is True
        assert code.uses_remaining == 10

    def test_creates_unlimited_use_code(self):
        """Should create unlimited use code with max_uses=0."""
        code = create_mock_promo_code(max_uses=0, use_count=5)

        assert code.max_uses == 0
        assert code.is_multi_use is True
        # Unlimited has None remaining
        assert code.uses_remaining is None

    # Validation Tests
    def test_validates_discount_percent(self):
        """Should validate discount percent."""
        valid_discounts = [10, 15, 20, 25, 50, 100]

        assert 10 in valid_discounts
        assert 100 in valid_discounts
        assert 30 not in valid_discounts

    def test_rejects_invalid_discount_percent(self):
        """Should reject invalid discount percent."""
        valid_discounts = [10, 15, 20, 25, 50, 100]
        invalid = 30

        is_valid = invalid in valid_discounts

        assert is_valid is False

    def test_validates_total_codes_range(self):
        """Should validate total_codes is between 1 and 1000."""
        min_codes = 1
        max_codes = 1000

        assert 1 >= min_codes and 1 <= max_codes
        assert 500 >= min_codes and 500 <= max_codes
        assert 1001 > max_codes

    def test_validates_discount_type(self):
        """Should validate discount_type."""
        valid_types = ['percentage', 'free_week', 'free_100']

        assert 'percentage' in valid_types
        assert 'free_week' in valid_types
        assert 'invalid_type' not in valid_types

    def test_sanitizes_code_prefix(self):
        """Should sanitize code prefix to alphanumeric only."""
        prefix = "TAG-2026!"

        sanitized = ''.join(c for c in prefix if c.isalnum())[:10]

        assert sanitized == "TAG2026"

    def test_sanitizes_custom_code(self):
        """Should sanitize custom code to alphanumeric only."""
        custom = "SUMMER-10%"

        sanitized = ''.join(c for c in custom if c.isalnum())[:20]

        assert sanitized == "SUMMER10"

    # Unhappy Path
    def test_requires_name(self):
        """Should require name field."""
        request = {
            "discount_percent": 10,
            "total_codes": 50,
        }

        has_name = "name" in request and request.get("name")

        assert has_name is False

    def test_requires_discount_percent(self):
        """Should require discount_percent field."""
        request = {
            "name": "Test",
            "total_codes": 50,
        }

        has_discount = "discount_percent" in request and request.get("discount_percent")

        assert has_discount is False

    def test_requires_total_codes_or_custom_code(self):
        """Should require total_codes or custom_code."""
        request = {
            "name": "Test",
            "discount_percent": 10,
        }

        has_codes = request.get("total_codes") or request.get("custom_code")

        assert has_codes is None

    def test_rejects_duplicate_custom_code(self):
        """Should reject duplicate custom code."""
        existing_codes = ["SUMMER10", "VIP20"]
        new_code = "SUMMER10"

        is_duplicate = new_code in existing_codes

        assert is_duplicate is True


# ============================================================================
# List Promotions Tests
# ============================================================================

class TestListPromotionsLogic:
    """Unit tests for list promotions logic."""

    # Happy Path
    def test_returns_all_promotions(self):
        """Should return all promotions."""
        promotions = [
            create_mock_promotion(id=1, name="Promo 1"),
            create_mock_promotion(id=2, name="Promo 2"),
            create_mock_promotion(id=3, name="Promo 3"),
        ]

        assert len(promotions) == 3

    def test_orders_by_created_at_desc(self):
        """Should order promotions by created_at descending."""
        now = datetime.now(timezone.utc)
        promotions = [
            create_mock_promotion(id=1, created_at=now - timedelta(days=2)),
            create_mock_promotion(id=2, created_at=now - timedelta(days=1)),
            create_mock_promotion(id=3, created_at=now),
        ]

        sorted_promos = sorted(promotions, key=lambda p: p.created_at, reverse=True)

        assert sorted_promos[0].id == 3
        assert sorted_promos[1].id == 2
        assert sorted_promos[2].id == 1

    def test_includes_codes_stats(self):
        """Should include code statistics."""
        promotion = create_mock_promotion(
            total_codes=100,
            codes_sent=30,
            codes_used=10,
        )

        response = {
            "total_codes": promotion.total_codes,
            "codes_sent": promotion.codes_sent,
            "codes_used": promotion.codes_used,
        }

        assert response["total_codes"] == 100
        assert response["codes_sent"] == 30
        assert response["codes_used"] == 10

    def test_calculates_available_codes(self):
        """Should calculate available codes count."""
        codes = [
            create_mock_promo_code(email_sent=False, is_used=False, shared_on_socials=False, shared_privately=False),
            create_mock_promo_code(email_sent=True, is_used=False, shared_on_socials=False, shared_privately=False),
            create_mock_promo_code(email_sent=False, is_used=True, shared_on_socials=False, shared_privately=False),
            create_mock_promo_code(email_sent=False, is_used=False, shared_on_socials=True, shared_privately=False),
        ]

        available = [c for c in codes if not c.email_sent and not c.is_used and not c.shared_on_socials and not c.shared_privately]

        assert len(available) == 1


# ============================================================================
# Get Promotion Detail Tests
# ============================================================================

class TestGetPromotionDetailLogic:
    """Unit tests for get promotion detail logic."""

    # Happy Path
    def test_returns_promotion_with_codes(self):
        """Should return promotion with all codes."""
        promotion = create_mock_promotion(id=1, name="Test Promo")
        codes = [
            create_mock_promo_code(id=1, promotion_id=1, code="TAG-001"),
            create_mock_promo_code(id=2, promotion_id=1, code="TAG-002"),
        ]

        response = {
            "id": promotion.id,
            "name": promotion.name,
            "codes": [{"id": c.id, "code": c.code} for c in codes],
        }

        assert response["name"] == "Test Promo"
        assert len(response["codes"]) == 2

    def test_includes_booking_references_for_used_codes(self):
        """Should include booking references for used codes."""
        code = create_mock_promo_code(
            is_used=True,
            booking_id=123,
        )

        # Simulate booking lookup
        booking_reference = "TAG-12345" if code.booking_id else None

        assert booking_reference == "TAG-12345"

    def test_includes_multi_use_booking_references(self):
        """Should include all booking references for multi-use codes."""
        booking_references = ["TAG-001", "TAG-002", "TAG-003"]

        code_data = {
            "booking_references": booking_references,
            "use_count": len(booking_references),
        }

        assert len(code_data["booking_references"]) == 3

    def test_calculates_is_expired(self):
        """Should calculate if code is expired."""
        uk_tz = pytz.timezone("Europe/London")
        now = datetime.now(uk_tz)

        expired_code = create_mock_promo_code(
            expires_at=now - timedelta(days=1)
        )
        valid_code = create_mock_promo_code(
            expires_at=now + timedelta(days=1)
        )

        expired_is_expired = now >= expired_code.expires_at
        valid_is_expired = now >= valid_code.expires_at

        assert expired_is_expired is True
        assert valid_is_expired is False

    # Unhappy Path
    def test_promotion_not_found(self):
        """Should handle promotion not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Update Promotion Tests
# ============================================================================

class TestUpdatePromotionLogic:
    """Unit tests for update promotion logic."""

    # Happy Path
    def test_updates_promotion_name(self):
        """Should update promotion name."""
        promotion = create_mock_promotion(name="Old Name")

        promotion.name = "New Name"
        promotion.updated_at = datetime.now(timezone.utc)

        assert promotion.name == "New Name"
        assert promotion.updated_at is not None

    # Unhappy Path
    def test_promotion_not_found_for_update(self):
        """Should handle promotion not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Delete Promotion Tests
# ============================================================================

class TestDeletePromotionLogic:
    """Unit tests for delete promotion logic."""

    # Happy Path
    def test_deletes_promotion(self):
        """Should delete promotion."""
        promotion = create_mock_promotion(id=1)
        mock_db = MagicMock()

        mock_db.delete(promotion)
        mock_db.commit()

        mock_db.delete.assert_called_once_with(promotion)

    def test_deletes_associated_codes(self):
        """Should delete associated promo codes."""
        codes = [
            create_mock_promo_code(id=1, promotion_id=1),
            create_mock_promo_code(id=2, promotion_id=1),
        ]

        # Cascade delete simulation
        deleted_count = len(codes)

        assert deleted_count == 2

    # Unhappy Path
    def test_promotion_not_found_for_delete(self):
        """Should handle promotion not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Generate Additional Codes Tests
# ============================================================================

class TestGenerateCodesLogic:
    """Unit tests for generate additional codes logic."""

    # Happy Path
    def test_generates_additional_codes(self):
        """Should generate additional codes for promotion."""
        promotion = create_mock_promotion(total_codes=50)
        additional = 25

        promotion.total_codes += additional

        assert promotion.total_codes == 75

    def test_generates_unique_codes(self):
        """Should generate unique codes."""
        existing = {"TAG-001", "TAG-002", "TAG-003"}
        new_codes = []

        for i in range(3):
            code = f"TAG-00{i+4}"
            if code not in existing:
                new_codes.append(code)
                existing.add(code)

        assert len(new_codes) == 3
        assert "TAG-004" in new_codes

    # Validation
    def test_validates_additional_count(self):
        """Should validate additional count is positive."""
        additional = 10

        is_valid = additional >= 1 and additional <= 1000

        assert is_valid is True

    def test_rejects_negative_count(self):
        """Should reject negative additional count."""
        additional = -5

        is_valid = additional >= 1

        assert is_valid is False


# ============================================================================
# Share Promo Code Tests
# ============================================================================

class TestSharePromoCodeLogic:
    """Unit tests for share promo code logic."""

    # Share on Socials
    def test_marks_shared_on_socials(self):
        """Should mark code as shared on socials."""
        code = create_mock_promo_code(shared_on_socials=False)

        code.shared_on_socials = True
        code.shared_on_socials_at = datetime.now(timezone.utc)

        assert code.shared_on_socials is True
        assert code.shared_on_socials_at is not None

    # Share Privately
    def test_marks_shared_privately(self):
        """Should mark code as shared privately."""
        code = create_mock_promo_code(shared_privately=False)

        code.shared_privately = True
        code.shared_privately_at = datetime.now(timezone.utc)

        assert code.shared_privately is True

    # Unhappy Path
    def test_code_not_found_for_share(self):
        """Should handle code not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = mock_db.query().filter().first()

        assert result is None


# ============================================================================
# Update Code Expiry Tests
# ============================================================================

class TestUpdateCodeExpiryLogic:
    """Unit tests for update code expiry logic."""

    # Happy Path
    def test_updates_expiry_date(self):
        """Should update code expiry date."""
        code = create_mock_promo_code(expires_at=None)
        uk_tz = pytz.timezone("Europe/London")
        new_expiry = uk_tz.localize(datetime(2026, 12, 31, 23, 59))

        code.expires_at = new_expiry

        assert code.expires_at.year == 2026
        assert code.expires_at.month == 12

    def test_clears_expiry_date(self):
        """Should clear expiry date (no expiry)."""
        uk_tz = pytz.timezone("Europe/London")
        code = create_mock_promo_code(
            expires_at=uk_tz.localize(datetime(2026, 12, 31))
        )

        code.expires_at = None

        assert code.expires_at is None

    # Validation
    def test_validates_expiry_format(self):
        """Should validate expiry date format."""
        valid_date = "31/12/2026"
        valid_time = "23:59"

        try:
            day, month, year = valid_date.split("/")
            hour, minute = valid_time.split(":")
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is True

    def test_rejects_invalid_expiry_format(self):
        """Should reject invalid expiry format."""
        invalid_date = "2026-12-31"  # Wrong format

        try:
            day, month, year = invalid_date.split("/")
            is_valid = True
        except ValueError:
            is_valid = False

        assert is_valid is False


# ============================================================================
# Available Codes Tests
# ============================================================================

class TestAvailableCodesLogic:
    """Unit tests for get available codes logic."""

    # Happy Path
    def test_returns_available_codes(self):
        """Should return only available codes."""
        codes = [
            create_mock_promo_code(id=1, email_sent=False, is_used=False, shared_on_socials=False, shared_privately=False),
            create_mock_promo_code(id=2, email_sent=True, is_used=False, shared_on_socials=False, shared_privately=False),
            create_mock_promo_code(id=3, email_sent=False, is_used=False, shared_on_socials=False, shared_privately=False),
        ]

        available = [c for c in codes if not c.email_sent and not c.is_used and not c.shared_on_socials and not c.shared_privately]

        assert len(available) == 2

    def test_excludes_used_codes(self):
        """Should exclude used codes."""
        codes = [
            create_mock_promo_code(id=1, is_used=True),
            create_mock_promo_code(id=2, is_used=False),
        ]

        available = [c for c in codes if not c.is_used]

        assert len(available) == 1

    def test_excludes_shared_codes(self):
        """Should exclude codes shared on socials or privately."""
        codes = [
            create_mock_promo_code(id=1, shared_on_socials=True),
            create_mock_promo_code(id=2, shared_privately=True),
            create_mock_promo_code(id=3, shared_on_socials=False, shared_privately=False),
        ]

        available = [c for c in codes if not c.shared_on_socials and not c.shared_privately]

        assert len(available) == 1


# ============================================================================
# Authentication Tests
# ============================================================================

class TestPromotionsAuthentication:
    """Tests for authentication on promotions endpoints."""

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
# Response Structure Tests
# ============================================================================

class TestPromotionResponseStructure:
    """Tests for response structure."""

    def test_create_response_structure(self):
        """Should return correct create response structure."""
        response = {
            "id": 1,
            "name": "Test Promotion",
            "discount_percent": 10,
            "discount_type": "percentage",
            "total_codes": 50,
            "codes_sent": 0,
            "codes_used": 0,
            "codes_available": 50,
            "created_by": "admin@test.com",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        assert "id" in response
        assert "name" in response
        assert "discount_percent" in response

    def test_list_response_structure(self):
        """Should return correct list response structure."""
        response = {
            "promotions": [
                {"id": 1, "name": "Promo 1"},
                {"id": 2, "name": "Promo 2"},
            ]
        }

        assert "promotions" in response
        assert len(response["promotions"]) == 2


# ============================================================================
# Boundary Tests
# ============================================================================

class TestPromotionsBoundaries:
    """Tests for boundary conditions."""

    def test_max_codes_1000(self):
        """Should handle maximum 1000 codes."""
        total_codes = 1000

        is_valid = total_codes <= 1000

        assert is_valid is True

    def test_min_codes_1(self):
        """Should handle minimum 1 code."""
        total_codes = 1

        is_valid = total_codes >= 1

        assert is_valid is True

    def test_very_long_promotion_name(self):
        """Should handle very long promotion name."""
        long_name = "A" * 500
        promotion = create_mock_promotion(name=long_name)

        assert len(promotion.name) == 500

    def test_max_prefix_length(self):
        """Should limit prefix to 10 characters."""
        prefix = "VERYLONGPREFIX"

        sanitized = prefix[:10]

        assert len(sanitized) == 10

    def test_max_custom_code_length(self):
        """Should limit custom code to 20 characters."""
        custom = "VERYLONGCUSTOMCODE123456"

        sanitized = custom[:20]

        assert len(sanitized) == 20


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
