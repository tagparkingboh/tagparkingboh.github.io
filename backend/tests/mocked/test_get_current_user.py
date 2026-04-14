"""
Mocked tests for get_current_user authentication dependency.

Tests the optimized JOIN query that validates session tokens and returns users.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from fastapi import HTTPException


class TestGetCurrentUserHappyPath:
    """Happy path tests for successful authentication."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def valid_user(self):
        """Create a valid active user."""
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.first_name = "Test"
        user.last_name = "User"
        user.is_admin = False
        user.is_active = True
        return user

    @pytest.fixture
    def admin_user(self):
        """Create a valid admin user."""
        user = Mock()
        user.id = 2
        user.email = "admin@example.com"
        user.first_name = "Admin"
        user.last_name = "User"
        user.is_admin = True
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, mock_db, valid_user):
        """Valid Bearer token should return the associated user."""
        from main import get_current_user

        # Mock the JOIN query to return the user
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        result = await get_current_user(
            authorization="Bearer valid_token_123",
            db=mock_db
        )

        assert result == valid_user
        assert result.email == "test@example.com"
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_admin_token_returns_admin_user(self, mock_db, admin_user):
        """Admin user token should return user with is_admin=True."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = admin_user

        result = await get_current_user(
            authorization="Bearer admin_token_456",
            db=mock_db
        )

        assert result == admin_user
        assert result.is_admin is True

    @pytest.mark.asyncio
    async def test_bearer_case_insensitive(self, mock_db, valid_user):
        """Bearer scheme should be case-insensitive."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        # Test lowercase "bearer"
        result = await get_current_user(
            authorization="bearer valid_token",
            db=mock_db
        )
        assert result == valid_user

    @pytest.mark.asyncio
    async def test_uses_join_query(self, mock_db, valid_user):
        """Should use JOIN query instead of separate queries."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        await get_current_user(
            authorization="Bearer token123",
            db=mock_db
        )

        # Verify query was called on User model
        mock_db.query.assert_called_once()
        # Verify join was called (the optimization)
        mock_query.join.assert_called_once()


class TestGetCurrentUserUnhappyPath:
    """Unhappy path tests for authentication failures."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_no_authorization_header(self, mock_db):
        """Missing Authorization header should raise 401."""
        from main import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None, db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Not authenticated"

    @pytest.mark.asyncio
    async def test_empty_authorization_header(self, mock_db):
        """Empty Authorization header should raise 401."""
        from main import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="", db=mock_db)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_format_no_bearer(self, mock_db):
        """Token without Bearer prefix should raise 401."""
        from main import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="token123", db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid authorization header"

    @pytest.mark.asyncio
    async def test_invalid_token_format_wrong_scheme(self, mock_db):
        """Wrong auth scheme (e.g., Basic) should raise 401."""
        from main import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Basic dXNlcjpwYXNz", db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid authorization header"

    @pytest.mark.asyncio
    async def test_invalid_token_format_extra_parts(self, mock_db):
        """Authorization with extra parts should raise 401."""
        from main import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer token extra", db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid authorization header"

    @pytest.mark.asyncio
    async def test_nonexistent_session(self, mock_db):
        """Token not in database should raise 401."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No user found

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer invalid_token", db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired session"

    @pytest.mark.asyncio
    async def test_expired_session(self, mock_db):
        """Expired session should raise 401 (handled by query filter)."""
        from main import get_current_user

        # When session is expired, the query filter returns None
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer expired_token", db=mock_db)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired session"

    @pytest.mark.asyncio
    async def test_inactive_user(self, mock_db):
        """Inactive user should raise 401 (handled by query filter)."""
        from main import get_current_user

        # When user is inactive, the query filter returns None
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer inactive_user_token", db=mock_db)

        assert exc_info.value.status_code == 401


class TestGetCurrentUserEdgeCases:
    """Edge case tests for authentication."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def valid_user(self):
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_bearer_with_leading_whitespace_works(self, mock_db, valid_user):
        """Leading whitespace is stripped by split(), so it works."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        # "  Bearer token123".split() gives ['Bearer', 'token123']
        result = await get_current_user(
            authorization="  Bearer token123",
            db=mock_db
        )
        assert result == valid_user

    @pytest.mark.asyncio
    async def test_token_with_special_characters(self, mock_db, valid_user):
        """Tokens with special characters should work."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        result = await get_current_user(
            authorization="Bearer abc123-def456_ghi789",
            db=mock_db
        )
        assert result == valid_user

    @pytest.mark.asyncio
    async def test_very_long_token(self, mock_db, valid_user):
        """Very long tokens should be handled."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        long_token = "a" * 1000
        result = await get_current_user(
            authorization=f"Bearer {long_token}",
            db=mock_db
        )
        assert result == valid_user

    @pytest.mark.asyncio
    async def test_empty_token_after_bearer(self, mock_db):
        """Empty token after Bearer should fail."""
        from main import get_current_user

        # "Bearer " with nothing after has only 1 part after split
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer ", db=mock_db)

        assert exc_info.value.status_code == 401


class TestGetCurrentUserBoundaries:
    """Boundary tests for authentication."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def valid_user(self):
        user = Mock()
        user.id = 1
        user.email = "test@example.com"
        user.is_active = True
        return user

    @pytest.mark.asyncio
    async def test_single_character_token(self, mock_db, valid_user):
        """Single character token should work."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        result = await get_current_user(
            authorization="Bearer x",
            db=mock_db
        )
        assert result == valid_user

    @pytest.mark.asyncio
    async def test_numeric_token(self, mock_db, valid_user):
        """Purely numeric token should work."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        result = await get_current_user(
            authorization="Bearer 123456789",
            db=mock_db
        )
        assert result == valid_user

    @pytest.mark.asyncio
    async def test_mixed_case_bearer(self, mock_db, valid_user):
        """Mixed case Bearer should work (e.g., BEARER, BeArEr)."""
        from main import get_current_user

        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = valid_user

        for bearer_case in ["BEARER", "BeArEr", "bEaReR"]:
            result = await get_current_user(
                authorization=f"{bearer_case} token123",
                db=mock_db
            )
            assert result == valid_user
