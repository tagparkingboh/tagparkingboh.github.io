"""
Tests for authentication endpoints.

Covers:
- User creation (admin endpoint)
- Login code request
- Login code verification
- Session management (logout, me)
- Negative testing and edge cases
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user(db_session):
    """Create a test user in the database."""
    from db_models import User

    user = User(
        email="test@tagparking.co.uk",
        first_name="Test",
        last_name="User",
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    """Create an admin test user in the database."""
    from db_models import User

    user = User(
        email="admin@tagparking.co.uk",
        first_name="Admin",
        last_name="User",
        is_admin=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def inactive_user(db_session):
    """Create an inactive test user in the database."""
    from db_models import User

    user = User(
        email="inactive@tagparking.co.uk",
        first_name="Inactive",
        last_name="User",
        is_admin=False,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def valid_login_code(db_session, test_user):
    """Create a valid login code for the test user."""
    from db_models import LoginCode

    code = LoginCode(
        user_id=test_user.id,
        code="123456",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        used=False,
    )
    db_session.add(code)
    db_session.commit()
    db_session.refresh(code)
    return code


@pytest.fixture
def expired_login_code(db_session, test_user):
    """Create an expired login code for the test user."""
    from db_models import LoginCode

    code = LoginCode(
        user_id=test_user.id,
        code="654321",
        expires_at=datetime.utcnow() - timedelta(minutes=5),  # Expired 5 mins ago
        used=False,
    )
    db_session.add(code)
    db_session.commit()
    db_session.refresh(code)
    return code


@pytest.fixture
def used_login_code(db_session, test_user):
    """Create a used login code for the test user."""
    from db_models import LoginCode

    code = LoginCode(
        user_id=test_user.id,
        code="111111",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        used=True,  # Already used
    )
    db_session.add(code)
    db_session.commit()
    db_session.refresh(code)
    return code


@pytest.fixture
def valid_session(db_session, test_user):
    """Create a valid session for the test user."""
    from db_models import Session as DbSession

    session = DbSession(
        user_id=test_user.id,
        token="valid_test_token_1234567890abcdef",
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def expired_session(db_session, test_user):
    """Create an expired session for the test user."""
    from db_models import Session as DbSession

    session = DbSession(
        user_id=test_user.id,
        token="expired_test_token_1234567890abcdef",
        expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


# =============================================================================
# User Creation Tests (Admin Endpoint)
# =============================================================================

class TestCreateUser:
    """Tests for POST /api/admin/users endpoint."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, client):
        """Should create a new user with valid secret."""
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "newuser@tagparking.co.uk",
                "first_name": "New",
                "last_name": "User",
                "is_admin": False,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["email"] == "newuser@tagparking.co.uk"
        assert data["user"]["first_name"] == "New"
        assert data["user"]["last_name"] == "User"
        assert data["user"]["is_admin"] is False

    @pytest.mark.asyncio
    async def test_create_admin_user(self, client):
        """Should create an admin user."""
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "newadmin@tagparking.co.uk",
                "first_name": "New",
                "last_name": "Admin",
                "is_admin": True,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["is_admin"] is True

    @pytest.mark.asyncio
    async def test_create_user_with_phone(self, client):
        """Should create a user with phone number."""
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "withphone@tagparking.co.uk",
                "first_name": "Phone",
                "last_name": "User",
                "phone": "+447123456789",
                "is_admin": False,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_create_user_invalid_secret(self, client):
        """Should reject creation with invalid secret."""
        response = await client.post(
            "/api/admin/users?secret=wrong-secret",
            json={
                "email": "newuser@tagparking.co.uk",
                "first_name": "New",
                "last_name": "User",
            }
        )

        assert response.status_code == 403
        assert "Invalid admin secret" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_missing_secret(self, client):
        """Should reject creation without secret."""
        response = await client.post(
            "/api/admin/users",
            json={
                "email": "newuser@tagparking.co.uk",
                "first_name": "New",
                "last_name": "User",
            }
        )

        assert response.status_code == 422  # Validation error - missing required query param

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, client, test_user):
        """Should reject creation with duplicate email."""
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": test_user.email,  # Same email as existing user
                "first_name": "Duplicate",
                "last_name": "User",
            }
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_email_normalized(self, client):
        """Should normalize email to lowercase."""
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "UPPERCASE@TAGPARKING.CO.UK",
                "first_name": "Upper",
                "last_name": "Case",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["email"] == "uppercase@tagparking.co.uk"

    @pytest.mark.asyncio
    async def test_create_user_whitespace_trimmed(self, client):
        """Should trim whitespace from names."""
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "whitespace@tagparking.co.uk",
                "first_name": "  Spaced  ",
                "last_name": "  Name  ",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["first_name"] == "Spaced"
        assert data["user"]["last_name"] == "Name"

    @pytest.mark.asyncio
    async def test_create_user_missing_required_fields(self, client):
        """Should reject creation with missing required fields."""
        # Missing last_name
        response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "incomplete@tagparking.co.uk",
                "first_name": "Incomplete",
            }
        )

        assert response.status_code == 422


# =============================================================================
# List Users Tests
# =============================================================================

class TestListUsers:
    """Tests for GET /api/admin/users endpoint."""

    @pytest.mark.asyncio
    async def test_list_users_success(self, client, test_user, admin_user):
        """Should list all users with valid secret."""
        response = await client.get("/api/admin/users?secret=tag-admin-2024")

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert len(data["users"]) >= 2  # At least our two test users

    @pytest.mark.asyncio
    async def test_list_users_invalid_secret(self, client):
        """Should reject listing with invalid secret."""
        response = await client.get("/api/admin/users?secret=wrong-secret")

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_empty(self, client):
        """Should return empty list when no users exist."""
        response = await client.get("/api/admin/users?secret=tag-admin-2024")

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert isinstance(data["users"], list)


# =============================================================================
# Request Code Tests
# =============================================================================

class TestRequestCode:
    """Tests for POST /api/auth/request-code endpoint."""

    @pytest.mark.asyncio
    async def test_request_code_valid_user(self, client, test_user):
        """Should send code for valid user (mocked email)."""
        with patch('main.send_login_code_email', return_value=True) as mock_email:
            response = await client.post(
                "/api/auth/request-code",
                json={"email": test_user.email}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "login code" in data["message"].lower()

            # Verify email was called
            mock_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_code_nonexistent_user(self, client):
        """Should return success even for non-existent user (security)."""
        with patch('main.send_login_code_email', return_value=True):
            response = await client.post(
                "/api/auth/request-code",
                json={"email": "nonexistent@tagparking.co.uk"}
            )

            # Should still return success to not leak user existence
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_request_code_inactive_user(self, client, inactive_user):
        """Should not send code to inactive user."""
        with patch('main.send_login_code_email', return_value=True) as mock_email:
            response = await client.post(
                "/api/auth/request-code",
                json={"email": inactive_user.email}
            )

            # Returns success (for security) but doesn't send email
            assert response.status_code == 200
            mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_request_code_email_normalized(self, client, test_user):
        """Should normalize email before lookup."""
        with patch('main.send_login_code_email', return_value=True) as mock_email:
            response = await client.post(
                "/api/auth/request-code",
                json={"email": test_user.email.upper()}  # Uppercase
            )

            assert response.status_code == 200
            mock_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_code_email_trimmed(self, client, test_user):
        """Should trim whitespace from email."""
        with patch('main.send_login_code_email', return_value=True) as mock_email:
            response = await client.post(
                "/api/auth/request-code",
                json={"email": f"  {test_user.email}  "}  # With whitespace
            )

            assert response.status_code == 200
            mock_email.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_code_invalidates_previous(self, client, test_user, valid_login_code, db_session):
        """Should invalidate previous unused codes."""
        from db_models import LoginCode

        with patch('main.send_login_code_email', return_value=True):
            response = await client.post(
                "/api/auth/request-code",
                json={"email": test_user.email}
            )

            assert response.status_code == 200

            # Check that old code is marked as used
            db_session.refresh(valid_login_code)
            assert valid_login_code.used is True

    @pytest.mark.asyncio
    async def test_request_code_email_send_failure(self, client, test_user):
        """Should still return success even if email fails (for security)."""
        with patch('main.send_login_code_email', return_value=False):
            response = await client.post(
                "/api/auth/request-code",
                json={"email": test_user.email}
            )

            # Still returns success to not leak information
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


# =============================================================================
# Verify Code Tests
# =============================================================================

class TestVerifyCode:
    """Tests for POST /api/auth/verify-code endpoint."""

    @pytest.mark.asyncio
    async def test_verify_code_success(self, client, test_user, valid_login_code):
        """Should verify valid code and create session."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": valid_login_code.code,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Login successful."
        assert data["token"] is not None
        assert len(data["token"]) == 64  # 32 bytes hex = 64 chars
        assert data["user"]["email"] == test_user.email
        assert data["user"]["first_name"] == test_user.first_name

    @pytest.mark.asyncio
    async def test_verify_code_invalid_code(self, client, test_user, valid_login_code):
        """Should reject invalid code."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": "000000",  # Wrong code
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "invalid" in data["message"].lower() or "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_verify_code_expired(self, client, test_user, expired_login_code):
        """Should reject expired code."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": expired_login_code.code,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "invalid" in data["message"].lower() or "expired" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_verify_code_already_used(self, client, test_user, used_login_code):
        """Should reject already used code."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": used_login_code.code,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_verify_code_wrong_user(self, client, admin_user, valid_login_code):
        """Should reject code for different user."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": admin_user.email,  # Different user
                "code": valid_login_code.code,  # Code belongs to test_user
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_verify_code_nonexistent_user(self, client, valid_login_code):
        """Should reject code for non-existent user."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": "nonexistent@tagparking.co.uk",
                "code": valid_login_code.code,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "invalid" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_verify_code_inactive_user(self, client, inactive_user, db_session):
        """Should reject code for inactive user."""
        from db_models import LoginCode

        # Create a valid code for inactive user
        code = LoginCode(
            user_id=inactive_user.id,
            code="999999",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
            used=False,
        )
        db_session.add(code)
        db_session.commit()

        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": inactive_user.email,
                "code": "999999",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_verify_code_marks_as_used(self, client, test_user, valid_login_code, db_session):
        """Should mark code as used after successful verification."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": valid_login_code.code,
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify code is now marked as used
        db_session.refresh(valid_login_code)
        assert valid_login_code.used is True

    @pytest.mark.asyncio
    async def test_verify_code_updates_last_login(self, client, test_user, valid_login_code, db_session):
        """Should update user's last_login timestamp."""
        original_last_login = test_user.last_login

        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": valid_login_code.code,
            }
        )

        assert response.status_code == 200

        db_session.refresh(test_user)
        assert test_user.last_login is not None
        if original_last_login:
            assert test_user.last_login > original_last_login

    @pytest.mark.asyncio
    async def test_verify_code_email_normalized(self, client, test_user, valid_login_code):
        """Should normalize email before lookup."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email.upper(),  # Uppercase
                "code": valid_login_code.code,
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_verify_code_whitespace_handled(self, client, test_user, valid_login_code):
        """Should handle whitespace in code."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": f" {valid_login_code.code} ",  # With whitespace
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is True


# =============================================================================
# Logout Tests
# =============================================================================

class TestLogout:
    """Tests for POST /api/auth/logout endpoint."""

    @pytest.mark.asyncio
    async def test_logout_success(self, client, valid_session, db_session):
        """Should invalidate session on logout."""
        from db_models import Session as DbSession

        response = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {valid_session.token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify session is deleted
        session = db_session.query(DbSession).filter(
            DbSession.token == valid_session.token
        ).first()
        assert session is None

    @pytest.mark.asyncio
    async def test_logout_no_token(self, client):
        """Should return success even without token."""
        response = await client.post("/api/auth/logout")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_logout_invalid_token(self, client):
        """Should return success even with invalid token."""
        response = await client.post(
            "/api/auth/logout",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_logout_malformed_header(self, client):
        """Should return success with malformed auth header."""
        response = await client.post(
            "/api/auth/logout",
            headers={"Authorization": "NotBearer token123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# =============================================================================
# Get Current User Tests
# =============================================================================

class TestGetMe:
    """Tests for GET /api/auth/me endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_success(self, client, test_user, valid_session):
        """Should return current user info."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {valid_session.token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["first_name"] == test_user.first_name
        assert data["last_name"] == test_user.last_name
        assert data["is_admin"] == test_user.is_admin

    @pytest.mark.asyncio
    async def test_get_me_admin_user(self, client, admin_user, db_session):
        """Should return is_admin=True for admin user."""
        from db_models import Session as DbSession

        # Create session for admin
        session = DbSession(
            user_id=admin_user.id,
            token="admin_test_token_1234567890abcdef",
            expires_at=datetime.utcnow() + timedelta(hours=8),
        )
        db_session.add(session)
        db_session.commit()

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {session.token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_admin"] is True

    @pytest.mark.asyncio
    async def test_get_me_no_token(self, client):
        """Should reject request without token."""
        response = await client.get("/api/auth/me")

        assert response.status_code == 401
        assert "Not authenticated" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client):
        """Should reject invalid token."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )

        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_me_expired_session(self, client, expired_session):
        """Should reject expired session."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_session.token}"}
        )

        assert response.status_code == 401
        assert "Invalid or expired" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_me_malformed_header(self, client):
        """Should reject malformed authorization header."""
        # Missing "Bearer" prefix
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "just_a_token"}
        )

        assert response.status_code == 401
        assert "Invalid authorization header" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_me_wrong_scheme(self, client, valid_session):
        """Should reject non-Bearer scheme."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Basic {valid_session.token}"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_inactive_user(self, client, inactive_user, db_session):
        """Should reject session for inactive user."""
        from db_models import Session as DbSession

        # Create session for inactive user
        session = DbSession(
            user_id=inactive_user.id,
            token="inactive_user_token_1234567890",
            expires_at=datetime.utcnow() + timedelta(hours=8),
        )
        db_session.add(session)
        db_session.commit()

        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {session.token}"}
        )

        assert response.status_code == 401
        assert "not found or inactive" in response.json()["detail"].lower()


# =============================================================================
# Integration Tests - Full Auth Flow
# =============================================================================

class TestAuthIntegration:
    """Integration tests for complete authentication flows."""

    @pytest.mark.asyncio
    async def test_full_login_flow(self, client, db_session):
        """Test complete login flow: create user -> request code -> verify -> access protected resource."""
        # 1. Create user
        create_response = await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "integration@tagparking.co.uk",
                "first_name": "Integration",
                "last_name": "Test",
                "is_admin": True,
            }
        )
        assert create_response.status_code == 200

        # 2. Request login code
        with patch('main.send_login_code_email', return_value=True):
            request_response = await client.post(
                "/api/auth/request-code",
                json={"email": "integration@tagparking.co.uk"}
            )
            assert request_response.status_code == 200

        # 3. Get the code from database (in real world, user gets it via email)
        from db_models import LoginCode, User
        user = db_session.query(User).filter(
            User.email == "integration@tagparking.co.uk"
        ).first()
        login_code = db_session.query(LoginCode).filter(
            LoginCode.user_id == user.id,
            LoginCode.used == False
        ).first()

        # 4. Verify code
        verify_response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": "integration@tagparking.co.uk",
                "code": login_code.code,
            }
        )
        assert verify_response.status_code == 200
        token = verify_response.json()["token"]

        # 5. Access protected resource
        me_response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "integration@tagparking.co.uk"

        # 6. Logout
        logout_response = await client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert logout_response.status_code == 200

        # 7. Token should no longer work
        final_me_response = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert final_me_response.status_code == 401

    @pytest.mark.asyncio
    async def test_multiple_code_requests_invalidate_previous(self, client, db_session):
        """Test that requesting new code invalidates previous ones."""
        # Create user
        await client.post(
            "/api/admin/users?secret=tag-admin-2024",
            json={
                "email": "multicode@tagparking.co.uk",
                "first_name": "Multi",
                "last_name": "Code",
            }
        )

        # Request first code
        with patch('main.send_login_code_email', return_value=True):
            await client.post(
                "/api/auth/request-code",
                json={"email": "multicode@tagparking.co.uk"}
            )

        # Get first code
        from db_models import LoginCode, User
        user = db_session.query(User).filter(
            User.email == "multicode@tagparking.co.uk"
        ).first()
        first_code = db_session.query(LoginCode).filter(
            LoginCode.user_id == user.id
        ).first()
        first_code_value = first_code.code

        # Request second code
        with patch('main.send_login_code_email', return_value=True):
            await client.post(
                "/api/auth/request-code",
                json={"email": "multicode@tagparking.co.uk"}
            )

        # First code should no longer work
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": "multicode@tagparking.co.uk",
                "code": first_code_value,
            }
        )
        assert response.json()["success"] is False

    @pytest.mark.asyncio
    async def test_code_single_use(self, client, test_user, valid_login_code):
        """Test that code can only be used once."""
        # First use - should succeed
        response1 = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": valid_login_code.code,
            }
        )
        assert response1.json()["success"] is True

        # Second use - should fail
        response2 = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": valid_login_code.code,
            }
        )
        assert response2.json()["success"] is False


# =============================================================================
# Edge Cases and Security Tests
# =============================================================================

class TestAuthSecurity:
    """Security-focused tests for authentication."""

    @pytest.mark.asyncio
    async def test_timing_attack_prevention_nonexistent_user(self, client):
        """Response should be similar for existent and non-existent users."""
        # This helps prevent timing attacks to enumerate users
        with patch('main.send_login_code_email', return_value=True):
            response = await client.post(
                "/api/auth/request-code",
                json={"email": "definitely_not_exists@example.com"}
            )

            # Should return success (same as real user)
            assert response.status_code == 200
            assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_sql_injection_email(self, client):
        """Should handle SQL injection attempts safely."""
        malicious_email = "test@example.com'; DROP TABLE users; --"

        response = await client.post(
            "/api/auth/request-code",
            json={"email": malicious_email}
        )

        # Should not crash, return normal response
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_very_long_email(self, client):
        """Should handle extremely long email addresses."""
        long_email = "a" * 1000 + "@example.com"

        response = await client.post(
            "/api/auth/request-code",
            json={"email": long_email}
        )

        # Should not crash
        assert response.status_code in [200, 422]

    @pytest.mark.asyncio
    async def test_special_characters_in_code(self, client, test_user):
        """Should handle special characters in code field."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": "12<script>alert('xss')</script>34",
            }
        )

        # Should not crash, just fail validation
        assert response.status_code == 200
        assert response.json()["success"] is False

    @pytest.mark.asyncio
    async def test_empty_code(self, client, test_user):
        """Should reject empty code."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": "",
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is False

    @pytest.mark.asyncio
    async def test_code_with_only_whitespace(self, client, test_user):
        """Should reject code that's only whitespace."""
        response = await client.post(
            "/api/auth/verify-code",
            json={
                "email": test_user.email,
                "code": "      ",
            }
        )

        assert response.status_code == 200
        assert response.json()["success"] is False

    @pytest.mark.asyncio
    async def test_concurrent_code_verification(self, client, test_user, valid_login_code):
        """Test concurrent verification attempts."""
        import asyncio

        async def verify():
            return await client.post(
                "/api/auth/verify-code",
                json={
                    "email": test_user.email,
                    "code": valid_login_code.code,
                }
            )

        # Run 5 concurrent verifications
        results = await asyncio.gather(*[verify() for _ in range(5)])

        # Only one should succeed
        successes = sum(1 for r in results if r.json().get("success"))
        assert successes == 1
