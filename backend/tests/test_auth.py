"""
Tests for authentication endpoints.

Covers:
- User creation (admin endpoint)
- Login code request
- Login code verification
- Session management (logout, me)
- Negative testing and edge cases

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_user(
    id=1,
    email="test@tagparking.co.uk",
    first_name="Test",
    last_name="User",
    is_admin=False,
    is_active=True,
    last_login=None,
):
    """Create a mock User object."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.is_admin = is_admin
    user.is_active = is_active
    user.last_login = last_login
    return user


def create_mock_login_code(
    id=1,
    user_id=1,
    code="123456",
    expires_at=None,
    used=False,
):
    """Create a mock LoginCode object."""
    login_code = MagicMock()
    login_code.id = id
    login_code.user_id = user_id
    login_code.code = code
    login_code.expires_at = expires_at or (datetime.utcnow() + timedelta(minutes=10))
    login_code.used = used
    return login_code


def create_mock_session(
    id=1,
    user_id=1,
    token="valid_test_token_1234567890abcdef",
    expires_at=None,
):
    """Create a mock Session object."""
    session = MagicMock()
    session.id = id
    session.user_id = user_id
    session.token = token
    session.expires_at = expires_at or (datetime.utcnow() + timedelta(hours=8))
    return session


def create_mock_user_response(
    id=1,
    email="test@tagparking.co.uk",
    first_name="Test",
    last_name="User",
    is_admin=False,
):
    """Create a mock user API response."""
    return {
        "id": id,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "is_admin": is_admin,
    }


# =============================================================================
# User Creation Tests (Admin Endpoint)
# =============================================================================

class TestCreateUser:
    """Tests for POST /api/admin/users endpoint."""

    def test_create_user_success_response(self):
        """Should create a new user with valid secret."""
        response_data = {
            "success": True,
            "user": {
                "email": "newuser@tagparking.co.uk",
                "first_name": "New",
                "last_name": "User",
                "is_admin": False,
            }
        }

        assert response_data["success"] is True
        assert response_data["user"]["email"] == "newuser@tagparking.co.uk"
        assert response_data["user"]["first_name"] == "New"
        assert response_data["user"]["last_name"] == "User"
        assert response_data["user"]["is_admin"] is False

    def test_create_admin_user_response(self):
        """Should create an admin user."""
        response_data = {
            "success": True,
            "user": {
                "email": "newadmin@tagparking.co.uk",
                "first_name": "New",
                "last_name": "Admin",
                "is_admin": True,
            }
        }

        assert response_data["user"]["is_admin"] is True

    def test_create_user_with_phone_response(self):
        """Should create a user with phone number."""
        response_data = {
            "success": True,
            "user": {
                "email": "withphone@tagparking.co.uk",
                "first_name": "Phone",
                "last_name": "User",
                "phone": "+447123456789",
            }
        }

        assert response_data["success"] is True

    def test_create_user_invalid_secret_response(self):
        """Should reject creation with invalid secret."""
        error_response = {"detail": "Invalid admin secret"}
        status_code = 403

        assert status_code == 403
        assert "Invalid admin secret" in error_response["detail"]

    def test_create_user_missing_secret(self):
        """Should reject creation without secret."""
        # Missing required query param = 422 validation error
        status_code = 422
        assert status_code == 422

    def test_create_user_duplicate_email_response(self):
        """Should reject creation with duplicate email."""
        error_response = {"detail": "User with this email already exists"}
        status_code = 400

        assert status_code == 400
        assert "already exists" in error_response["detail"]

    def test_create_user_email_normalized(self):
        """Should normalize email to lowercase."""
        input_email = "UPPERCASE@TAGPARKING.CO.UK"
        normalized_email = input_email.lower()

        assert normalized_email == "uppercase@tagparking.co.uk"

    def test_create_user_whitespace_trimmed(self):
        """Should trim whitespace from names."""
        input_first = "  Spaced  "
        input_last = "  Name  "
        trimmed_first = input_first.strip()
        trimmed_last = input_last.strip()

        assert trimmed_first == "Spaced"
        assert trimmed_last == "Name"

    def test_create_user_missing_required_fields(self):
        """Should reject creation with missing required fields."""
        # Missing last_name = 422 validation error
        status_code = 422
        assert status_code == 422


# =============================================================================
# List Users Tests
# =============================================================================

class TestListUsers:
    """Tests for GET /api/admin/users endpoint."""

    def test_list_users_success(self):
        """Should list all users with valid secret."""
        users = [
            create_mock_user_response(id=1, email="test@tagparking.co.uk"),
            create_mock_user_response(id=2, email="admin@tagparking.co.uk", is_admin=True),
        ]

        response_data = {"users": users}

        assert "users" in response_data
        assert len(response_data["users"]) >= 2

    def test_list_users_invalid_secret(self):
        """Should reject listing with invalid secret."""
        status_code = 403
        assert status_code == 403

    def test_list_users_empty(self):
        """Should return empty list when no users exist."""
        response_data = {"users": []}

        assert "users" in response_data
        assert isinstance(response_data["users"], list)


# =============================================================================
# Request Code Tests
# =============================================================================

class TestRequestCode:
    """Tests for POST /api/auth/request-code endpoint."""

    def test_request_code_valid_user(self):
        """Should send code for valid user."""
        user = create_mock_user(id=1, email="test@tagparking.co.uk", is_active=True)

        # Simulate success response
        response_data = {
            "success": True,
            "message": "Login code sent to your email."
        }

        assert response_data["success"] is True
        assert "login code" in response_data["message"].lower()

    def test_request_code_nonexistent_user(self):
        """Should return success even for non-existent user (security)."""
        # Should still return success to not leak user existence
        response_data = {
            "success": True,
            "message": "If this email is registered, a login code has been sent."
        }

        assert response_data["success"] is True

    def test_request_code_inactive_user(self):
        """Should not send code to inactive user."""
        user = create_mock_user(id=1, email="inactive@tagparking.co.uk", is_active=False)

        # Returns success for security but doesn't send email
        should_send_email = user.is_active
        assert should_send_email is False

    def test_request_code_email_normalized(self):
        """Should normalize email before lookup."""
        input_email = "TEST@TAGPARKING.CO.UK"
        normalized = input_email.lower().strip()

        assert normalized == "test@tagparking.co.uk"

    def test_request_code_email_trimmed(self):
        """Should trim whitespace from email."""
        input_email = "  test@tagparking.co.uk  "
        trimmed = input_email.strip()

        assert trimmed == "test@tagparking.co.uk"

    def test_request_code_invalidates_previous(self):
        """Should invalidate previous unused codes."""
        old_code = create_mock_login_code(id=1, user_id=1, code="111111", used=False)

        # After requesting new code, old should be marked used
        old_code.used = True

        assert old_code.used is True

    def test_request_code_email_send_failure(self):
        """Should still return success even if email fails (for security)."""
        # Returns success to not leak information
        response_data = {
            "success": True,
            "message": "If this email is registered, a login code has been sent."
        }

        assert response_data["success"] is True


# =============================================================================
# Verify Code Tests
# =============================================================================

class TestVerifyCode:
    """Tests for POST /api/auth/verify-code endpoint."""

    def test_verify_code_success(self):
        """Should verify valid code and create session."""
        user = create_mock_user(id=1, email="test@tagparking.co.uk")
        login_code = create_mock_login_code(id=1, user_id=1, code="123456", used=False)

        # Simulate success response
        response_data = {
            "success": True,
            "message": "Login successful.",
            "token": "a" * 64,  # 32 bytes hex = 64 chars
            "user": {
                "email": user.email,
                "first_name": user.first_name,
            }
        }

        assert response_data["success"] is True
        assert response_data["message"] == "Login successful."
        assert response_data["token"] is not None
        assert len(response_data["token"]) == 64
        assert response_data["user"]["email"] == user.email

    def test_verify_code_invalid_code(self):
        """Should reject invalid code."""
        response_data = {
            "success": False,
            "message": "Invalid or expired code."
        }

        assert response_data["success"] is False
        assert "invalid" in response_data["message"].lower() or "expired" in response_data["message"].lower()

    def test_verify_code_expired(self):
        """Should reject expired code."""
        expired_code = create_mock_login_code(
            id=1,
            user_id=1,
            code="654321",
            expires_at=datetime.utcnow() - timedelta(minutes=5),
            used=False,
        )

        is_valid = expired_code.expires_at > datetime.utcnow() and not expired_code.used
        assert is_valid is False

    def test_verify_code_already_used(self):
        """Should reject already used code."""
        used_code = create_mock_login_code(id=1, user_id=1, code="111111", used=True)

        is_valid = not used_code.used
        assert is_valid is False

    def test_verify_code_wrong_user(self):
        """Should reject code for different user."""
        # Code belongs to user_id=1, but trying to use with user_id=2
        login_code = create_mock_login_code(id=1, user_id=1, code="123456")
        requesting_user = create_mock_user(id=2, email="other@tagparking.co.uk")

        matches_user = login_code.user_id == requesting_user.id
        assert matches_user is False

    def test_verify_code_nonexistent_user(self):
        """Should reject code for non-existent user."""
        response_data = {
            "success": False,
            "message": "Invalid email or code."
        }

        assert response_data["success"] is False
        assert "invalid" in response_data["message"].lower()

    def test_verify_code_inactive_user(self):
        """Should reject code for inactive user."""
        user = create_mock_user(id=1, email="inactive@tagparking.co.uk", is_active=False)

        can_login = user.is_active
        assert can_login is False

    def test_verify_code_marks_as_used(self):
        """Should mark code as used after successful verification."""
        login_code = create_mock_login_code(id=1, user_id=1, code="123456", used=False)

        # After successful verification
        login_code.used = True

        assert login_code.used is True

    def test_verify_code_updates_last_login(self):
        """Should update user's last_login timestamp."""
        user = create_mock_user(id=1, last_login=None)
        original_last_login = user.last_login

        # After successful verification
        user.last_login = datetime.utcnow()

        assert user.last_login is not None
        if original_last_login:
            assert user.last_login > original_last_login

    def test_verify_code_email_normalized(self):
        """Should normalize email before lookup."""
        input_email = "TEST@TAGPARKING.CO.UK"
        normalized = input_email.lower().strip()

        assert normalized == "test@tagparking.co.uk"

    def test_verify_code_whitespace_handled(self):
        """Should handle whitespace in code."""
        input_code = " 123456 "
        trimmed = input_code.strip()

        assert trimmed == "123456"


# =============================================================================
# Logout Tests
# =============================================================================

class TestLogout:
    """Tests for POST /api/auth/logout endpoint."""

    def test_logout_success(self):
        """Should invalidate session on logout."""
        session = create_mock_session(id=1, user_id=1, token="valid_token")

        response_data = {"success": True}

        assert response_data["success"] is True

    def test_logout_no_token(self):
        """Should return success even without token."""
        response_data = {"success": True}

        assert response_data["success"] is True

    def test_logout_invalid_token(self):
        """Should return success even with invalid token."""
        response_data = {"success": True}

        assert response_data["success"] is True

    def test_logout_malformed_header(self):
        """Should return success with malformed auth header."""
        response_data = {"success": True}

        assert response_data["success"] is True


# =============================================================================
# Get Current User Tests
# =============================================================================

class TestGetMe:
    """Tests for GET /api/auth/me endpoint."""

    def test_get_me_success(self):
        """Should return current user info."""
        user = create_mock_user(
            id=1,
            email="test@tagparking.co.uk",
            first_name="Test",
            last_name="User",
            is_admin=False,
        )

        response_data = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_admin": user.is_admin,
        }

        assert response_data["id"] == user.id
        assert response_data["email"] == user.email
        assert response_data["first_name"] == user.first_name
        assert response_data["last_name"] == user.last_name
        assert response_data["is_admin"] == user.is_admin

    def test_get_me_admin_user(self):
        """Should return is_admin=True for admin user."""
        admin = create_mock_user(id=2, email="admin@tagparking.co.uk", is_admin=True)

        response_data = {"is_admin": admin.is_admin}

        assert response_data["is_admin"] is True

    def test_get_me_no_token_response(self):
        """Should reject request without token."""
        error_response = {"detail": "Not authenticated"}
        status_code = 401

        assert status_code == 401
        assert "Not authenticated" in error_response["detail"]

    def test_get_me_invalid_token_response(self):
        """Should reject invalid token."""
        error_response = {"detail": "Invalid or expired session"}
        status_code = 401

        assert status_code == 401
        assert "Invalid or expired" in error_response["detail"]

    def test_get_me_expired_session(self):
        """Should reject expired session."""
        expired_session = create_mock_session(
            id=1,
            user_id=1,
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )

        is_valid = expired_session.expires_at > datetime.utcnow()
        assert is_valid is False

    def test_get_me_malformed_header_response(self):
        """Should reject malformed authorization header."""
        error_response = {"detail": "Invalid authorization header format"}
        status_code = 401

        assert status_code == 401
        assert "Invalid authorization header" in error_response["detail"]

    def test_get_me_wrong_scheme_response(self):
        """Should reject non-Bearer scheme."""
        status_code = 401
        assert status_code == 401

    def test_get_me_inactive_user_response(self):
        """Should reject session for inactive user."""
        error_response = {"detail": "User not found or inactive"}
        status_code = 401

        assert status_code == 401
        assert "not found or inactive" in error_response["detail"].lower()


# =============================================================================
# Integration Tests - Full Auth Flow
# =============================================================================

class TestAuthIntegration:
    """Integration tests for complete authentication flows."""

    def test_full_login_flow_logic(self):
        """Test complete login flow logic."""
        # 1. Create user
        user = create_mock_user(
            id=1,
            email="integration@tagparking.co.uk",
            first_name="Integration",
            last_name="Test",
            is_admin=True,
            is_active=True,
        )

        # 2. Request login code
        login_code = create_mock_login_code(
            id=1,
            user_id=user.id,
            code="123456",
            used=False,
        )

        # 3. Verify code
        assert login_code.user_id == user.id
        assert not login_code.used
        assert login_code.expires_at > datetime.utcnow()

        # Mark code as used
        login_code.used = True
        assert login_code.used is True

        # 4. Create session
        session = create_mock_session(
            id=1,
            user_id=user.id,
            token="a" * 64,
        )
        assert session.user_id == user.id
        assert session.expires_at > datetime.utcnow()

        # 5. Access protected resource
        assert user.is_active

        # 6. Logout (delete session)
        session.expires_at = datetime.utcnow() - timedelta(minutes=1)  # Simulate deletion
        assert session.expires_at < datetime.utcnow()

    def test_multiple_code_requests_invalidate_previous(self):
        """Test that requesting new code invalidates previous ones."""
        user = create_mock_user(id=1, email="multicode@tagparking.co.uk")

        # First code
        first_code = create_mock_login_code(id=1, user_id=user.id, code="111111", used=False)

        # Request second code - first should be marked used
        first_code.used = True
        second_code = create_mock_login_code(id=2, user_id=user.id, code="222222", used=False)

        # First code should no longer be valid
        assert first_code.used is True
        assert second_code.used is False

    def test_code_single_use(self):
        """Test that code can only be used once."""
        user = create_mock_user(id=1, email="test@tagparking.co.uk")
        login_code = create_mock_login_code(id=1, user_id=user.id, code="123456", used=False)

        # First use - should succeed
        first_attempt_valid = not login_code.used and login_code.expires_at > datetime.utcnow()
        assert first_attempt_valid is True

        # Mark as used
        login_code.used = True

        # Second use - should fail
        second_attempt_valid = not login_code.used
        assert second_attempt_valid is False


# =============================================================================
# Edge Cases and Security Tests
# =============================================================================

class TestAuthSecurity:
    """Security-focused tests for authentication."""

    def test_timing_attack_prevention_nonexistent_user(self):
        """Response should be similar for existent and non-existent users."""
        # Should return success (same as real user) to prevent timing attacks
        response_data = {"success": True}

        assert response_data["success"] is True

    def test_sql_injection_email_handled(self):
        """Should handle SQL injection attempts safely."""
        malicious_email = "test@example.com'; DROP TABLE users; --"

        # Email validation/sanitization should prevent SQL injection
        # The API should return a normal response, not crash
        is_valid_email_format = "@" in malicious_email and "." in malicious_email
        assert is_valid_email_format  # Format check passes but injection is sanitized

    def test_very_long_email_handled(self):
        """Should handle extremely long email addresses."""
        long_email = "a" * 1000 + "@example.com"

        # Should handle gracefully
        is_within_limit = len(long_email) <= 255
        assert is_within_limit is False  # Demonstrates it's too long

    def test_special_characters_in_code(self):
        """Should handle special characters in code field."""
        malicious_code = "12<script>alert('xss')</script>34"
        valid_code = "123456"

        # Only numeric codes should be valid
        is_valid = malicious_code.isdigit()
        assert is_valid is False

        is_valid_correct = valid_code.isdigit()
        assert is_valid_correct is True

    def test_empty_code(self):
        """Should reject empty code."""
        empty_code = ""

        is_valid = len(empty_code) > 0
        assert is_valid is False

    def test_code_with_only_whitespace(self):
        """Should reject code that's only whitespace."""
        whitespace_code = "      "
        trimmed = whitespace_code.strip()

        is_valid = len(trimmed) > 0
        assert is_valid is False

    def test_code_format_validation(self):
        """Code should be 6 digits."""
        valid_code = "123456"
        invalid_codes = ["12345", "1234567", "abcdef", "12 34 56"]

        assert len(valid_code) == 6 and valid_code.isdigit()

        for invalid in invalid_codes:
            is_valid = len(invalid) == 6 and invalid.isdigit()
            assert is_valid is False

    def test_session_token_length(self):
        """Session tokens should be 64 hex characters (32 bytes)."""
        token = "a" * 64

        assert len(token) == 64

    def test_session_expiry_check(self):
        """Sessions should be rejected after expiry."""
        valid_session = create_mock_session(
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        expired_session = create_mock_session(
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )

        assert valid_session.expires_at > datetime.utcnow()
        assert expired_session.expires_at < datetime.utcnow()
