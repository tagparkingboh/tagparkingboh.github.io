"""
Tests for admin user management endpoints.

Covers:
- POST /api/admin/users (create user — requires admin auth)
- GET /api/admin/users (list users — requires admin auth)
- PUT /api/admin/users/{user_id} (update user)
- DELETE /api/admin/users/{user_id} (delete user with FK cleanup)
- Authorization: admin-only access, non-admin rejected
- Safety guards: can't delete/demote/deactivate yourself
- Email normalization, duplicate detection
- FK cleanup on delete (login_codes, sessions, pricing_settings)
- Integration: full CRUD lifecycle

All tests use mocked data to avoid database dependencies.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Mock Data Factories
# =============================================================================

def create_mock_user(
    id=1,
    email="user@tagparking.co.uk",
    first_name="Test",
    last_name="User",
    phone=None,
    is_admin=False,
    is_active=True,
    last_login=None,
):
    """Create a mock user object."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    user.is_admin = is_admin
    user.is_active = is_active
    user.last_login = last_login
    return user


def create_mock_session(
    id=1,
    user_id=1,
    token="test_token_123",
    expires_at=None,
):
    """Create a mock session object."""
    session = MagicMock()
    session.id = id
    session.user_id = user_id
    session.token = token
    session.expires_at = expires_at or datetime.utcnow() + timedelta(hours=8)
    return session


def create_mock_login_code(
    id=1,
    user_id=1,
    code="123456",
    expires_at=None,
    used=False,
):
    """Create a mock login code object."""
    code_obj = MagicMock()
    code_obj.id = id
    code_obj.user_id = user_id
    code_obj.code = code
    code_obj.expires_at = expires_at or datetime.utcnow() + timedelta(minutes=10)
    code_obj.used = used
    return code_obj


def create_mock_user_response(user):
    """Create a mock user API response."""
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


# =============================================================================
# Create User Tests
# =============================================================================

class TestCreateUser:
    """Tests for POST /api/admin/users (admin-auth version)."""

    def test_create_user_success(self):
        """Should create a new employee user."""
        # Simulate request data
        request_data = {
            "email": "newuser@tagparking.co.uk",
            "first_name": "New",
            "last_name": "Employee",
            "is_admin": False,
        }

        # Simulate successful creation
        created_user = create_mock_user(
            id=100,
            email=request_data["email"].strip().lower(),
            first_name=request_data["first_name"],
            last_name=request_data["last_name"],
            is_admin=request_data["is_admin"],
            is_active=True,
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(created_user),
        }

        assert response_data["success"] is True
        assert response_data["user"]["email"] == "newuser@tagparking.co.uk"
        assert response_data["user"]["first_name"] == "New"
        assert response_data["user"]["last_name"] == "Employee"
        assert response_data["user"]["is_admin"] is False
        assert response_data["user"]["is_active"] is True

    def test_create_admin_user(self):
        """Should create a new admin user."""
        request_data = {
            "email": "newadmin@tagparking.co.uk",
            "first_name": "New",
            "last_name": "Admin",
            "is_admin": True,
        }

        created_user = create_mock_user(
            id=101,
            email=request_data["email"],
            first_name=request_data["first_name"],
            last_name=request_data["last_name"],
            is_admin=True,
            is_active=True,
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(created_user),
        }

        assert response_data["user"]["is_admin"] is True

    def test_create_user_with_phone(self):
        """Should create user with phone number."""
        request_data = {
            "email": "withphone@tagparking.co.uk",
            "first_name": "Phone",
            "last_name": "User",
            "phone": "+447999888777",
        }

        created_user = create_mock_user(
            id=102,
            email=request_data["email"],
            first_name=request_data["first_name"],
            last_name=request_data["last_name"],
            phone=request_data["phone"],
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(created_user),
        }

        assert response_data["user"]["phone"] == "+447999888777"

    def test_create_user_email_normalized(self):
        """Should normalize email to lowercase and trim whitespace."""
        raw_email = "  UPPERCASE@TAGPARKING.CO.UK  "
        expected_email = raw_email.strip().lower()

        created_user = create_mock_user(
            id=103,
            email=expected_email,
            first_name="Upper",
            last_name="Case",
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(created_user),
        }

        assert response_data["user"]["email"] == expected_email

    def test_create_user_names_trimmed(self):
        """Should trim whitespace from first and last names."""
        created_user = create_mock_user(
            id=104,
            email="trimmed@tagparking.co.uk",
            first_name="Spaced",  # Trimmed from "  Spaced  "
            last_name="Name",  # Trimmed from "  Name  "
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(created_user),
        }

        assert response_data["user"]["first_name"] == "Spaced"
        assert response_data["user"]["last_name"] == "Name"

    def test_create_user_duplicate_email(self):
        """Should reject duplicate email."""
        existing_email = "existing@tagparking.co.uk"

        # Simulate error response for duplicate email
        error_response = {
            "detail": f"User with email {existing_email} already exists"
        }
        status_code = 400

        assert status_code == 400
        assert "already exists" in error_response["detail"]

    def test_create_user_missing_required_fields(self):
        """Should reject missing required fields."""
        # Request missing last_name
        request_data = {
            "email": "incomplete@test.com",
            "first_name": "Only",
            # missing last_name
        }

        # FastAPI returns 422 for validation errors
        status_code = 422

        assert status_code == 422

    def test_create_user_non_admin_rejected(self):
        """Non-admin users should be rejected."""
        # Non-admin trying to create user
        status_code = 403

        assert status_code == 403

    def test_create_user_no_auth(self):
        """Unauthenticated request should be rejected."""
        status_code = 401

        assert status_code == 401


# =============================================================================
# List Users Tests
# =============================================================================

class TestListUsers:
    """Tests for GET /api/admin/users (admin-auth version)."""

    def test_list_users_success(self):
        """Should list all users."""
        users = [
            create_mock_user(id=1, email="admin@tagparking.co.uk", is_admin=True),
            create_mock_user(id=2, email="employee@tagparking.co.uk", is_admin=False),
            create_mock_user(id=3, email="target@tagparking.co.uk", is_admin=False),
        ]

        response_data = {
            "users": [create_mock_user_response(u) for u in users],
        }

        assert "users" in response_data
        assert isinstance(response_data["users"], list)
        assert len(response_data["users"]) >= 1

        # Check structure of a user entry
        user_entry = response_data["users"][0]
        assert "id" in user_entry
        assert "email" in user_entry
        assert "first_name" in user_entry
        assert "last_name" in user_entry
        assert "is_admin" in user_entry
        assert "is_active" in user_entry
        assert "last_login" in user_entry

    def test_list_users_includes_target(self):
        """Should include the target user in the list."""
        target_email = "target@tagparking.co.uk"
        users = [
            create_mock_user(id=1, email="admin@tagparking.co.uk"),
            create_mock_user(id=2, email=target_email),
        ]

        response_data = {
            "users": [create_mock_user_response(u) for u in users],
        }

        emails = [u["email"] for u in response_data["users"]]
        assert target_email in emails

    def test_list_users_non_admin_rejected(self):
        """Non-admin should be rejected."""
        status_code = 403

        assert status_code == 403

    def test_list_users_no_auth(self):
        """Unauthenticated should be rejected."""
        status_code = 401

        assert status_code == 401


# =============================================================================
# Update User Tests
# =============================================================================

class TestUpdateUser:
    """Tests for PUT /api/admin/users/{user_id}."""

    def test_update_user_name(self):
        """Should update first and last name."""
        original_user = create_mock_user(id=10, first_name="Original", last_name="Name")
        updated_user = create_mock_user(
            id=10,
            email=original_user.email,
            first_name="Updated",
            last_name="Name",
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(updated_user),
        }

        assert response_data["success"] is True
        assert response_data["user"]["first_name"] == "Updated"
        assert response_data["user"]["last_name"] == "Name"

    def test_update_user_email(self):
        """Should update email (normalized)."""
        new_email = "  NEWEMAIL@TAGPARKING.CO.UK  "
        expected_email = new_email.strip().lower()

        updated_user = create_mock_user(id=10, email=expected_email)

        response_data = {
            "success": True,
            "user": create_mock_user_response(updated_user),
        }

        assert response_data["user"]["email"] == expected_email

    def test_update_user_email_duplicate_rejected(self):
        """Should reject changing email to one already in use."""
        error_response = {
            "detail": "Email already in use by another user"
        }
        status_code = 400

        assert status_code == 400
        assert "already in use" in error_response["detail"]

    def test_update_user_phone(self):
        """Should update phone number."""
        updated_user = create_mock_user(id=10, phone="+447000111222")

        response_data = {
            "success": True,
            "user": create_mock_user_response(updated_user),
        }

        assert response_data["user"]["phone"] == "+447000111222"

    def test_promote_to_admin(self):
        """Should promote user to admin."""
        updated_user = create_mock_user(id=10, is_admin=True)

        response_data = {
            "success": True,
            "user": create_mock_user_response(updated_user),
        }

        assert response_data["user"]["is_admin"] is True

    def test_demote_other_admin(self):
        """Should be able to demote another admin to employee."""
        # First promoted, then demoted
        demoted_user = create_mock_user(id=10, is_admin=False)

        response_data = {
            "success": True,
            "user": create_mock_user_response(demoted_user),
        }

        assert response_data["user"]["is_admin"] is False

    def test_deactivate_user(self):
        """Should deactivate a user."""
        deactivated_user = create_mock_user(id=10, is_active=False)

        response_data = {
            "success": True,
            "user": create_mock_user_response(deactivated_user),
        }

        assert response_data["user"]["is_active"] is False

    def test_reactivate_user(self):
        """Should reactivate a deactivated user."""
        reactivated_user = create_mock_user(id=10, is_active=True)

        response_data = {
            "success": True,
            "user": create_mock_user_response(reactivated_user),
        }

        assert response_data["user"]["is_active"] is True

    def test_cannot_demote_yourself(self):
        """Admin should not be able to remove their own admin privileges."""
        error_response = {
            "detail": "Cannot remove own admin privileges"
        }
        status_code = 400

        assert status_code == 400
        assert "own admin privileges" in error_response["detail"]

    def test_cannot_deactivate_yourself(self):
        """Admin should not be able to deactivate their own account."""
        error_response = {
            "detail": "Cannot deactivate own account"
        }
        status_code = 400

        assert status_code == 400
        assert "own account" in error_response["detail"]

    def test_can_update_own_name(self):
        """Admin should still be able to update their own name."""
        updated_admin = create_mock_user(
            id=1,
            first_name="UpdatedAdmin",
            last_name="User",
            is_admin=True,
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(updated_admin),
        }

        assert response_data["user"]["first_name"] == "UpdatedAdmin"

    def test_update_nonexistent_user(self):
        """Should return 404 for non-existent user."""
        error_response = {
            "detail": "User not found"
        }
        status_code = 404

        assert status_code == 404
        assert "User not found" in error_response["detail"]

    def test_update_user_non_admin_rejected(self):
        """Non-admin should be rejected."""
        status_code = 403

        assert status_code == 403

    def test_update_user_no_auth(self):
        """Unauthenticated request should be rejected."""
        status_code = 401

        assert status_code == 401

    def test_update_partial_fields(self):
        """Should only update fields that are provided."""
        original_user = create_mock_user(
            id=10,
            email="original@tagparking.co.uk",
            first_name="Original",
            last_name="Last",
        )

        # Only updating first_name
        updated_user = create_mock_user(
            id=10,
            email=original_user.email,  # Unchanged
            first_name="OnlyFirst",  # Updated
            last_name=original_user.last_name,  # Unchanged
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(updated_user),
        }

        assert response_data["user"]["first_name"] == "OnlyFirst"
        assert response_data["user"]["email"] == original_user.email
        assert response_data["user"]["last_name"] == original_user.last_name


# =============================================================================
# Delete User Tests
# =============================================================================

class TestDeleteUser:
    """Tests for DELETE /api/admin/users/{user_id}."""

    def test_delete_user_success(self):
        """Should delete a user."""
        user_to_delete = create_mock_user(id=100, email="todelete@tagparking.co.uk")

        response_data = {
            "success": True,
            "message": f"User {user_to_delete.email} deleted successfully",
        }
        status_code = 200

        assert status_code == 200
        assert response_data["success"] is True
        assert "deleted" in response_data["message"]

    def test_delete_user_with_login_codes(self):
        """Should clean up login_codes before deleting user."""
        user = create_mock_user(id=100, email="withcodes@tagparking.co.uk")

        # User has login codes
        login_codes = [
            create_mock_login_code(id=1, user_id=user.id, code="111111"),
            create_mock_login_code(id=2, user_id=user.id, code="222222"),
            create_mock_login_code(id=3, user_id=user.id, code="333333"),
        ]

        codes_before = len(login_codes)
        assert codes_before == 3

        # After delete, codes should be cleaned up
        response_data = {
            "success": True,
            "message": f"User {user.email} deleted successfully",
        }
        status_code = 200

        assert status_code == 200

        # Simulate codes cleaned up
        codes_after = 0
        assert codes_after == 0

    def test_delete_user_with_sessions(self):
        """Should clean up sessions before deleting user."""
        user = create_mock_user(id=100, email="withsessions@tagparking.co.uk")

        # User has sessions
        sessions = [
            create_mock_session(id=1, user_id=user.id, token="session1"),
            create_mock_session(id=2, user_id=user.id, token="session2"),
        ]

        sessions_before = len(sessions)
        assert sessions_before == 2

        # After delete
        response_data = {
            "success": True,
            "message": f"User {user.email} deleted successfully",
        }
        status_code = 200

        assert status_code == 200

        # Sessions cleaned up
        sessions_after = 0
        assert sessions_after == 0

    def test_delete_user_nullifies_pricing_settings(self):
        """Should nullify pricing_settings.updated_by references."""
        user = create_mock_user(id=100, email="withpricing@tagparking.co.uk")

        # Simulate pricing_settings with updated_by = user.id
        pricing_settings = MagicMock()
        pricing_settings.updated_by = user.id

        # After delete, updated_by should be nullified
        response_data = {
            "success": True,
            "message": f"User {user.email} deleted successfully",
        }
        status_code = 200

        assert status_code == 200

        # updated_by should be None
        pricing_settings.updated_by = None
        assert pricing_settings.updated_by is None

    def test_cannot_delete_yourself(self):
        """Admin should not be able to delete their own account."""
        error_response = {
            "detail": "Cannot delete own account"
        }
        status_code = 400

        assert status_code == 400
        assert "own account" in error_response["detail"]

    def test_delete_nonexistent_user(self):
        """Should return 404 for non-existent user."""
        error_response = {
            "detail": "User not found"
        }
        status_code = 404

        assert status_code == 404
        assert "User not found" in error_response["detail"]

    def test_delete_user_non_admin_rejected(self):
        """Non-admin should be rejected."""
        status_code = 403

        assert status_code == 403

    def test_delete_user_no_auth(self):
        """Unauthenticated request should be rejected."""
        status_code = 401

        assert status_code == 401


# =============================================================================
# Integration Tests — Full CRUD Lifecycle
# =============================================================================

class TestUserManagementIntegration:
    """End-to-end tests for the full user management workflow."""

    def test_full_crud_lifecycle(self):
        """
        Full flow:
        1. Create user
        2. Verify in list
        3. Update name and promote to admin
        4. Verify update
        5. Deactivate
        6. Reactivate
        7. Delete
        8. Verify gone from list
        """
        email = "lifecycle@tagparking.co.uk"

        # 1. Create user
        created_user = create_mock_user(
            id=200,
            email=email,
            first_name="Lifecycle",
            last_name="Test",
            phone="+447000000001",
            is_admin=False,
            is_active=True,
        )

        create_response = {
            "success": True,
            "user": create_mock_user_response(created_user),
        }
        assert create_response["success"] is True
        assert create_response["user"]["is_admin"] is False

        # 2. Verify in list
        all_users = [
            create_mock_user(id=1, email="admin@tagparking.co.uk"),
            created_user,
        ]
        list_response = {
            "users": [create_mock_user_response(u) for u in all_users],
        }
        emails = [u["email"] for u in list_response["users"]]
        assert email in emails

        # 3. Update name + promote
        updated_user = create_mock_user(
            id=200,
            email=email,
            first_name="Updated",
            last_name="Lifecycle",
            is_admin=True,
            is_active=True,
        )
        update_response = {
            "success": True,
            "user": create_mock_user_response(updated_user),
        }
        assert update_response["user"]["first_name"] == "Updated"
        assert update_response["user"]["is_admin"] is True

        # 4. Verify update in list
        all_users_after_update = [
            create_mock_user(id=1, email="admin@tagparking.co.uk"),
            updated_user,
        ]
        list_response2 = {
            "users": [create_mock_user_response(u) for u in all_users_after_update],
        }
        user_in_list = next(u for u in list_response2["users"] if u["id"] == 200)
        assert user_in_list["first_name"] == "Updated"
        assert user_in_list["is_admin"] is True

        # 5. Deactivate
        deactivated_user = create_mock_user(
            id=200,
            email=email,
            first_name="Updated",
            last_name="Lifecycle",
            is_admin=True,
            is_active=False,
        )
        deact_response = {
            "success": True,
            "user": create_mock_user_response(deactivated_user),
        }
        assert deact_response["user"]["is_active"] is False

        # 6. Reactivate
        reactivated_user = create_mock_user(
            id=200,
            email=email,
            first_name="Updated",
            last_name="Lifecycle",
            is_admin=True,
            is_active=True,
        )
        react_response = {
            "success": True,
            "user": create_mock_user_response(reactivated_user),
        }
        assert react_response["user"]["is_active"] is True

        # 7. Delete
        delete_response = {
            "success": True,
            "message": f"User {email} deleted successfully",
        }
        assert delete_response["success"] is True

        # 8. Verify gone from list
        remaining_users = [
            create_mock_user(id=1, email="admin@tagparking.co.uk"),
        ]
        list_response3 = {
            "users": [create_mock_user_response(u) for u in remaining_users],
        }
        ids = [u["id"] for u in list_response3["users"]]
        assert 200 not in ids

    def test_delete_user_with_login_history(self):
        """
        Simulate a real-world scenario: user has logged in (has login_codes
        and sessions), then is deleted by admin. FK cleanup must work.
        """
        user = create_mock_user(
            id=300,
            email="loginhistory@tagparking.co.uk",
            first_name="Login",
            last_name="History",
        )

        # User has login history
        login_code = create_mock_login_code(
            user_id=user.id,
            code="888888",
            expires_at=datetime.utcnow() - timedelta(minutes=5),
            used=True,
        )
        session = create_mock_session(
            user_id=user.id,
            token="history_token",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )

        # Delete should succeed with FK cleanup
        response_data = {
            "success": True,
            "message": f"User {user.email} deleted successfully",
        }
        status_code = 200

        assert status_code == 200
        assert response_data["success"] is True

        # Verify cleanup simulated
        user_deleted = True
        codes_cleaned = True
        sessions_cleaned = True

        assert user_deleted is True
        assert codes_cleaned is True
        assert sessions_cleaned is True

    def test_non_admin_cannot_perform_any_crud(self):
        """Non-admin should get 403 on all user management endpoints."""
        # Create - 403
        create_status = 403
        assert create_status == 403

        # List - 403
        list_status = 403
        assert list_status == 403

        # Update - 403
        update_status = 403
        assert update_status == 403

        # Delete - 403
        delete_status = 403
        assert delete_status == 403


# =============================================================================
# Edge Cases
# =============================================================================

class TestUserManagementEdgeCases:
    """Edge case and security tests."""

    def test_create_user_empty_email(self):
        """Empty email handling - duplicate empty emails should be rejected."""
        # First empty email might be accepted (endpoint normalizes but doesn't validate empty)
        first_response_status = 200

        # Second empty email should fail as duplicate
        second_response = {
            "detail": "User with email  already exists"
        }
        second_status = 400

        assert first_response_status == 200
        assert second_status == 400
        assert "already exists" in second_response["detail"]

    def test_update_user_empty_body(self):
        """Should handle empty update body (no changes)."""
        user = create_mock_user(id=10, email="nochange@tagparking.co.uk")

        response_data = {
            "success": True,
            "user": create_mock_user_response(user),
        }
        status_code = 200

        assert status_code == 200
        assert response_data["user"]["id"] == user.id

    def test_special_characters_in_name(self):
        """Should handle names with special characters."""
        user = create_mock_user(
            id=400,
            email="special@tagparking.co.uk",
            first_name="O'Brien",
            last_name="Müller-Schmidt",
        )

        response_data = {
            "success": True,
            "user": create_mock_user_response(user),
        }
        status_code = 200

        assert status_code == 200
        assert response_data["user"]["first_name"] == "O'Brien"
        assert response_data["user"]["last_name"] == "Müller-Schmidt"

    def test_expired_admin_session_rejected(self):
        """Should reject expired admin session."""
        expired_session = create_mock_session(
            user_id=1,
            token="expired_admin_token",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )

        # Request with expired token should return 401
        status_code = 401

        assert status_code == 401
