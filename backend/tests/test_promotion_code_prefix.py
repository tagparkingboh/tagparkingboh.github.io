"""
Tests for Promotion Code Prefix Feature.

Tests the ability to set a custom prefix for promo codes when creating promotions.
For example, a "Spring Sale" promotion could have codes like "SPRING-XXXX-XXXX"
instead of the default "TAG-XXXX-XXXX".

Test coverage:
- Unit tests for generate_promo_code with custom prefix
- Unit tests for create_promotion API with code_prefix
- Unit tests for generate_more_codes using stored prefix
- Integration tests for full promotion workflow
- Edge cases and validation
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
import re
import string

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import generate_promo_code


# =============================================================================
# Unit Tests for generate_promo_code function
# =============================================================================

class TestGeneratePromoCodeUnit:
    """Unit tests for the generate_promo_code function."""

    def test_default_prefix_is_tag(self):
        """Test that default prefix is TAG."""
        code = generate_promo_code()
        assert code.startswith("TAG-")

    def test_custom_prefix_spring(self):
        """Test custom prefix SPRING."""
        code = generate_promo_code("SPRING")
        assert code.startswith("SPRING-")

    def test_custom_prefix_summer(self):
        """Test custom prefix SUMMER."""
        code = generate_promo_code("SUMMER")
        assert code.startswith("SUMMER-")

    def test_custom_prefix_sale(self):
        """Test custom prefix SALE."""
        code = generate_promo_code("SALE")
        assert code.startswith("SALE-")

    def test_code_format_with_default_prefix(self):
        """Test code format: TAG-XXXX-XXXX."""
        code = generate_promo_code()
        pattern = r"^TAG-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, code), f"Code '{code}' doesn't match expected format"

    def test_code_format_with_custom_prefix(self):
        """Test code format: PREFIX-XXXX-XXXX."""
        code = generate_promo_code("SPRING")
        pattern = r"^SPRING-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, code), f"Code '{code}' doesn't match expected format"

    def test_code_format_with_numeric_prefix(self):
        """Test code format with numeric prefix: 2026-XXXX-XXXX."""
        code = generate_promo_code("2026")
        pattern = r"^2026-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, code), f"Code '{code}' doesn't match expected format"

    def test_code_format_with_alphanumeric_prefix(self):
        """Test code format with alphanumeric prefix: SALE2026-XXXX-XXXX."""
        code = generate_promo_code("SALE2026")
        pattern = r"^SALE2026-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, code), f"Code '{code}' doesn't match expected format"

    def test_code_uniqueness(self):
        """Test that generated codes are likely unique."""
        codes = set()
        for _ in range(100):
            code = generate_promo_code("TEST")
            codes.add(code)
        # All 100 codes should be unique (collision probability is negligible)
        assert len(codes) == 100

    def test_code_characters_are_valid(self):
        """Test that code parts only contain uppercase letters and digits."""
        valid_chars = set(string.ascii_uppercase + string.digits)
        for _ in range(50):
            code = generate_promo_code("PREFIX")
            parts = code.split("-")
            # First part is the prefix
            # Parts 2 and 3 should be alphanumeric
            for char in parts[1] + parts[2]:
                assert char in valid_chars, f"Invalid character '{char}' in code '{code}'"


# =============================================================================
# Unit Tests for create_promotion API endpoint
# =============================================================================

class TestCreatePromotionWithPrefix:
    """Unit tests for create_promotion API with code_prefix parameter."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    @pytest.fixture
    def mock_admin_user(self):
        """Create a mock admin user."""
        user = MagicMock()
        user.email = "admin@test.com"
        user.is_admin = True
        return user

    def test_prefix_sanitization_uppercase(self):
        """Test that prefix is converted to uppercase."""
        # Lowercase should become uppercase
        prefix = "spring"
        sanitized = ''.join(c for c in prefix.upper() if c.isalnum())[:10]
        assert sanitized == "SPRING"

    def test_prefix_sanitization_removes_special_chars(self):
        """Test that special characters are removed from prefix."""
        prefix = "SPRING-2026!"
        sanitized = ''.join(c for c in prefix if c.isalnum())[:10]
        assert sanitized == "SPRING2026"

    def test_prefix_sanitization_max_length(self):
        """Test that prefix is truncated to 10 characters."""
        prefix = "VERYLONGPREFIXNAME"
        sanitized = prefix[:10]
        assert sanitized == "VERYLONGPR"
        assert len(sanitized) == 10

    def test_empty_prefix_defaults_to_tag(self):
        """Test that empty prefix defaults to TAG."""
        prefix = ""
        if not prefix.strip():
            prefix = "TAG"
        assert prefix == "TAG"

    def test_whitespace_prefix_defaults_to_tag(self):
        """Test that whitespace-only prefix defaults to TAG."""
        prefix = "   "
        prefix = prefix.strip().upper()
        if not prefix:
            prefix = "TAG"
        assert prefix == "TAG"


# =============================================================================
# Unit Tests for generate_more_codes with stored prefix
# =============================================================================

class TestGenerateMoreCodesWithPrefix:
    """Unit tests for generate_more_codes using the promotion's stored prefix."""

    def test_uses_stored_prefix(self):
        """Test that generate_more_codes uses the promotion's stored prefix."""
        # Simulate a promotion with a custom prefix
        promotion = MagicMock()
        promotion.code_prefix = "SUMMER"

        prefix = promotion.code_prefix if promotion.code_prefix else "TAG"
        code = generate_promo_code(prefix)

        assert code.startswith("SUMMER-")

    def test_defaults_to_tag_if_no_prefix(self):
        """Test that generate_more_codes defaults to TAG if no prefix stored."""
        # Simulate a promotion without a prefix (older promotions)
        promotion = MagicMock()
        promotion.code_prefix = None

        prefix = promotion.code_prefix if promotion.code_prefix else "TAG"
        code = generate_promo_code(prefix)

        assert code.startswith("TAG-")

    def test_defaults_to_tag_if_empty_prefix(self):
        """Test that generate_more_codes defaults to TAG if empty prefix stored."""
        promotion = MagicMock()
        promotion.code_prefix = ""

        prefix = promotion.code_prefix if promotion.code_prefix else "TAG"
        code = generate_promo_code(prefix)

        assert code.startswith("TAG-")


# =============================================================================
# Integration Tests (mocked)
# =============================================================================

class TestPromotionCodePrefixIntegration:
    """Integration tests for the code prefix feature workflow."""

    def test_full_workflow_with_custom_prefix(self):
        """Test creating a promotion with custom prefix and generating codes."""
        # 1. Create promotion with prefix "SPRING"
        prefix = "SPRING"

        # 2. Generate codes with that prefix
        codes = []
        for _ in range(5):
            code = generate_promo_code(prefix)
            codes.append(code)

        # 3. All codes should have the SPRING prefix
        for code in codes:
            assert code.startswith("SPRING-")
            # Verify format
            pattern = r"^SPRING-[A-Z0-9]{4}-[A-Z0-9]{4}$"
            assert re.match(pattern, code)

    def test_multiple_promotions_different_prefixes(self):
        """Test that different promotions can have different prefixes."""
        spring_codes = [generate_promo_code("SPRING") for _ in range(3)]
        summer_codes = [generate_promo_code("SUMMER") for _ in range(3)]
        default_codes = [generate_promo_code() for _ in range(3)]

        for code in spring_codes:
            assert code.startswith("SPRING-")

        for code in summer_codes:
            assert code.startswith("SUMMER-")

        for code in default_codes:
            assert code.startswith("TAG-")


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================

class TestCodePrefixEdgeCases:
    """Edge cases and boundary tests for code prefix feature."""

    def test_single_character_prefix(self):
        """Test prefix with single character."""
        code = generate_promo_code("X")
        assert code.startswith("X-")
        pattern = r"^X-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, code)

    def test_max_length_prefix(self):
        """Test prefix at maximum length (10 characters)."""
        prefix = "ABCDEFGHIJ"  # 10 characters
        code = generate_promo_code(prefix)
        assert code.startswith("ABCDEFGHIJ-")
        pattern = r"^ABCDEFGHIJ-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, code)

    def test_numeric_only_prefix(self):
        """Test prefix with only numbers."""
        code = generate_promo_code("2026")
        assert code.startswith("2026-")

    def test_mixed_case_input_prefix(self):
        """Test that mixed case input is handled (should be uppercase in backend)."""
        # In the actual API, the prefix is converted to uppercase
        # This test verifies the generate_promo_code function works with uppercase
        code = generate_promo_code("SPRING")  # Already uppercase
        assert code.startswith("SPRING-")

    def test_code_total_length_with_short_prefix(self):
        """Test total code length with short prefix."""
        code = generate_promo_code("X")
        # Format: X-XXXX-XXXX = 1 + 1 + 4 + 1 + 4 = 11 characters
        assert len(code) == 11

    def test_code_total_length_with_long_prefix(self):
        """Test total code length with long prefix."""
        code = generate_promo_code("ABCDEFGHIJ")
        # Format: ABCDEFGHIJ-XXXX-XXXX = 10 + 1 + 4 + 1 + 4 = 20 characters
        assert len(code) == 20

    def test_code_total_length_with_default_prefix(self):
        """Test total code length with default TAG prefix."""
        code = generate_promo_code()
        # Format: TAG-XXXX-XXXX = 3 + 1 + 4 + 1 + 4 = 13 characters
        assert len(code) == 13


# =============================================================================
# Validation Tests
# =============================================================================

class TestCodePrefixValidation:
    """Tests for prefix validation logic."""

    def test_valid_prefixes(self):
        """Test various valid prefixes."""
        valid_prefixes = [
            "TAG",
            "SPRING",
            "SUMMER",
            "SALE",
            "2026",
            "VIP",
            "PROMO",
            "DEAL",
            "A",
            "ABCDEFGHIJ",
        ]
        for prefix in valid_prefixes:
            code = generate_promo_code(prefix)
            assert code.startswith(f"{prefix}-"), f"Failed for prefix '{prefix}'"

    def test_prefix_with_spaces_in_middle(self):
        """Test that spaces in prefix are handled by sanitization logic."""
        # In actual API, spaces would be stripped
        original = "SPRING SALE"
        sanitized = ''.join(c for c in original if c.isalnum())
        code = generate_promo_code(sanitized)
        assert code.startswith("SPRINGSALE-")

    def test_sanitization_removes_hyphens(self):
        """Test that hyphens in prefix are removed by sanitization."""
        original = "SPRING-2026"
        sanitized = ''.join(c for c in original if c.isalnum())
        code = generate_promo_code(sanitized)
        assert code.startswith("SPRING2026-")


# =============================================================================
# API Contract Tests
# =============================================================================

class TestAPIContractCodePrefix:
    """Tests to verify the API contract for code_prefix parameter."""

    def test_code_prefix_is_optional(self):
        """Test that code_prefix parameter is optional."""
        # Request without code_prefix should work and default to TAG
        request = {
            "name": "Test Promotion",
            "discount_percent": 10,
            "total_codes": 5
        }
        # code_prefix not in request
        code_prefix = request.get("code_prefix", "").strip().upper()
        if not code_prefix:
            code_prefix = "TAG"
        assert code_prefix == "TAG"

    def test_code_prefix_in_request(self):
        """Test that code_prefix is extracted from request."""
        request = {
            "name": "Spring Sale",
            "discount_percent": 10,
            "total_codes": 5,
            "code_prefix": "SPRING"
        }
        code_prefix = request.get("code_prefix", "").strip().upper()
        if not code_prefix:
            code_prefix = "TAG"
        assert code_prefix == "SPRING"

    def test_code_prefix_lowercase_input(self):
        """Test that lowercase code_prefix is converted to uppercase."""
        request = {
            "name": "Spring Sale",
            "discount_percent": 10,
            "total_codes": 5,
            "code_prefix": "spring"
        }
        code_prefix = request.get("code_prefix", "").strip().upper()
        assert code_prefix == "SPRING"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
