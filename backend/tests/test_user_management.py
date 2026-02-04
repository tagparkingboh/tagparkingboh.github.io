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
"""
import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing."""
    from db_models import User
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"admin-mgmt-{unique}@tagparking.co.uk",
        first_name="Admin",
        last_name="Manager",
        is_admin=True,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    # Cleanup
    from db_models import Session as DbSession, LoginCode, VehicleInspection
    db_session.query(VehicleInspection).filter(VehicleInspection.inspector_id == user.id).delete()
    db_session.query(LoginCode).filter(LoginCode.user_id == user.id).delete()
    db_session.query(DbSession).filter(DbSession.user_id == user.id).delete()
    db_session.commit()
    # Re-check user still exists (may have been deleted by test)
    existing = db_session.query(User).filter(User.id == user.id).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()


@pytest.fixture
def admin_session(db_session, admin_user):
    """Create a valid session for the admin user."""
    from db_models import Session as DbSession
    session = DbSession(
        user_id=admin_user.id,
        token=f"admin_mgmt_{uuid.uuid4().hex}",
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    yield session


@pytest.fixture
def admin_headers(admin_session):
    """Return authorization headers for the admin."""
    return {"Authorization": f"Bearer {admin_session.token}"}


@pytest.fixture
def non_admin_user(db_session):
    """Create a non-admin (employee) user."""
    from db_models import User
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"employee-mgmt-{unique}@tagparking.co.uk",
        first_name="Employee",
        last_name="Regular",
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    from db_models import Session as DbSession, LoginCode, VehicleInspection
    db_session.query(VehicleInspection).filter(VehicleInspection.inspector_id == user.id).delete()
    db_session.query(LoginCode).filter(LoginCode.user_id == user.id).delete()
    db_session.query(DbSession).filter(DbSession.user_id == user.id).delete()
    db_session.commit()
    existing = db_session.query(User).filter(User.id == user.id).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()


@pytest.fixture
def non_admin_session(db_session, non_admin_user):
    """Create a valid session for the non-admin user."""
    from db_models import Session as DbSession
    session = DbSession(
        user_id=non_admin_user.id,
        token=f"emp_mgmt_{uuid.uuid4().hex}",
        expires_at=datetime.utcnow() + timedelta(hours=8),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    yield session


@pytest.fixture
def non_admin_headers(non_admin_session):
    """Return authorization headers for the non-admin user."""
    return {"Authorization": f"Bearer {non_admin_session.token}"}


@pytest.fixture
def target_user(db_session):
    """Create a user that will be the target of update/delete operations."""
    from db_models import User
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"target-{unique}@tagparking.co.uk",
        first_name="Target",
        last_name="User",
        phone="+447111222333",
        is_admin=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    yield user
    from db_models import Session as DbSession, LoginCode, VehicleInspection
    db_session.query(VehicleInspection).filter(VehicleInspection.inspector_id == user.id).delete()
    db_session.query(LoginCode).filter(LoginCode.user_id == user.id).delete()
    db_session.query(DbSession).filter(DbSession.user_id == user.id).delete()
    db_session.commit()
    existing = db_session.query(User).filter(User.id == user.id).first()
    if existing:
        db_session.delete(existing)
        db_session.commit()


# =============================================================================
# Create User Tests
# =============================================================================

class TestCreateUser:
    """Tests for POST /api/admin/users (admin-auth version)."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, client, admin_headers, db_session):
        """Should create a new employee user."""
        unique = uuid.uuid4().hex[:8]
        email = f"newuser-{unique}@tagparking.co.uk"

        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "first_name": "New",
                "last_name": "Employee",
                "is_admin": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["email"] == email
        assert data["user"]["first_name"] == "New"
        assert data["user"]["last_name"] == "Employee"
        assert data["user"]["is_admin"] is False
        assert data["user"]["is_active"] is True

        # Cleanup
        from db_models import User
        created = db_session.query(User).filter(User.email == email).first()
        if created:
            db_session.delete(created)
            db_session.commit()

    @pytest.mark.asyncio
    async def test_create_admin_user(self, client, admin_headers, db_session):
        """Should create a new admin user."""
        unique = uuid.uuid4().hex[:8]
        email = f"newadmin-{unique}@tagparking.co.uk"

        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "first_name": "New",
                "last_name": "Admin",
                "is_admin": True,
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["is_admin"] is True

        from db_models import User
        created = db_session.query(User).filter(User.email == email).first()
        if created:
            db_session.delete(created)
            db_session.commit()

    @pytest.mark.asyncio
    async def test_create_user_with_phone(self, client, admin_headers, db_session):
        """Should create user with phone number."""
        unique = uuid.uuid4().hex[:8]
        email = f"withphone-{unique}@tagparking.co.uk"

        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "first_name": "Phone",
                "last_name": "User",
                "phone": "+447999888777",
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["phone"] == "+447999888777"

        from db_models import User
        created = db_session.query(User).filter(User.email == email).first()
        if created:
            db_session.delete(created)
            db_session.commit()

    @pytest.mark.asyncio
    async def test_create_user_email_normalized(self, client, admin_headers, db_session):
        """Should normalize email to lowercase and trim whitespace."""
        unique = uuid.uuid4().hex[:8]
        raw_email = f"  UPPERCASE-{unique}@TAGPARKING.CO.UK  "
        expected = raw_email.strip().lower()

        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": raw_email,
                "first_name": "Upper",
                "last_name": "Case",
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == expected

        from db_models import User
        created = db_session.query(User).filter(User.email == expected).first()
        if created:
            db_session.delete(created)
            db_session.commit()

    @pytest.mark.asyncio
    async def test_create_user_names_trimmed(self, client, admin_headers, db_session):
        """Should trim whitespace from first and last names."""
        unique = uuid.uuid4().hex[:8]
        email = f"trimmed-{unique}@tagparking.co.uk"

        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "first_name": "  Spaced  ",
                "last_name": "  Name  ",
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["first_name"] == "Spaced"
        assert response.json()["user"]["last_name"] == "Name"

        from db_models import User
        created = db_session.query(User).filter(User.email == email).first()
        if created:
            db_session.delete(created)
            db_session.commit()

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, client, admin_headers, target_user):
        """Should reject duplicate email."""
        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": target_user.email,
                "first_name": "Duplicate",
                "last_name": "Email",
            },
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_user_missing_required_fields(self, client, admin_headers):
        """Should reject missing required fields."""
        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": "incomplete@test.com",
                "first_name": "Only",
                # missing last_name
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_user_non_admin_rejected(self, client, non_admin_headers):
        """Non-admin users should be rejected."""
        response = await client.post(
            "/api/admin/users",
            headers=non_admin_headers,
            json={
                "email": "should-fail@test.com",
                "first_name": "Fail",
                "last_name": "User",
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_no_auth(self, client):
        """Unauthenticated request should be rejected."""
        response = await client.post(
            "/api/admin/users",
            json={
                "email": "noauth@test.com",
                "first_name": "No",
                "last_name": "Auth",
            },
        )

        assert response.status_code == 401


# =============================================================================
# List Users Tests
# =============================================================================

class TestListUsers:
    """Tests for GET /api/admin/users (admin-auth version)."""

    @pytest.mark.asyncio
    async def test_list_users_success(self, client, admin_headers, target_user):
        """Should list all users."""
        response = await client.get(
            "/api/admin/users",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) >= 1

        # Check structure of a user entry
        user_entry = data["users"][0]
        assert "id" in user_entry
        assert "email" in user_entry
        assert "first_name" in user_entry
        assert "last_name" in user_entry
        assert "is_admin" in user_entry
        assert "is_active" in user_entry
        assert "last_login" in user_entry

    @pytest.mark.asyncio
    async def test_list_users_includes_target(self, client, admin_headers, target_user):
        """Should include the target user in the list."""
        response = await client.get(
            "/api/admin/users",
            headers=admin_headers,
        )

        emails = [u["email"] for u in response.json()["users"]]
        assert target_user.email in emails

    @pytest.mark.asyncio
    async def test_list_users_non_admin_rejected(self, client, non_admin_headers):
        """Non-admin should be rejected."""
        response = await client.get(
            "/api/admin/users",
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_no_auth(self, client):
        """Unauthenticated should be rejected."""
        response = await client.get("/api/admin/users")
        assert response.status_code == 401


# =============================================================================
# Update User Tests
# =============================================================================

class TestUpdateUser:
    """Tests for PUT /api/admin/users/{user_id}."""

    @pytest.mark.asyncio
    async def test_update_user_name(self, client, admin_headers, target_user):
        """Should update first and last name."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={
                "first_name": "Updated",
                "last_name": "Name",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["first_name"] == "Updated"
        assert data["user"]["last_name"] == "Name"

    @pytest.mark.asyncio
    async def test_update_user_email(self, client, admin_headers, target_user, db_session):
        """Should update email (normalized)."""
        unique = uuid.uuid4().hex[:8]
        new_email = f"  NEWEMAIL-{unique}@TAGPARKING.CO.UK  "

        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"email": new_email},
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == new_email.strip().lower()

    @pytest.mark.asyncio
    async def test_update_user_email_duplicate_rejected(self, client, admin_headers, target_user, admin_user):
        """Should reject changing email to one already in use."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"email": admin_user.email},
        )

        assert response.status_code == 400
        assert "already in use" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_phone(self, client, admin_headers, target_user):
        """Should update phone number."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"phone": "+447000111222"},
        )

        assert response.status_code == 200
        assert response.json()["user"]["phone"] == "+447000111222"

    @pytest.mark.asyncio
    async def test_promote_to_admin(self, client, admin_headers, target_user):
        """Should promote user to admin."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"is_admin": True},
        )

        assert response.status_code == 200
        assert response.json()["user"]["is_admin"] is True

    @pytest.mark.asyncio
    async def test_demote_other_admin(self, client, admin_headers, target_user):
        """Should be able to demote another admin to employee."""
        # First promote
        await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"is_admin": True},
        )

        # Then demote
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"is_admin": False},
        )

        assert response.status_code == 200
        assert response.json()["user"]["is_admin"] is False

    @pytest.mark.asyncio
    async def test_deactivate_user(self, client, admin_headers, target_user):
        """Should deactivate a user."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"is_active": False},
        )

        assert response.status_code == 200
        assert response.json()["user"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_reactivate_user(self, client, admin_headers, target_user):
        """Should reactivate a deactivated user."""
        # Deactivate
        await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"is_active": False},
        )

        # Reactivate
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"is_active": True},
        )

        assert response.status_code == 200
        assert response.json()["user"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_cannot_demote_yourself(self, client, admin_headers, admin_user):
        """Admin should not be able to remove their own admin privileges."""
        response = await client.put(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_headers,
            json={"is_admin": False},
        )

        assert response.status_code == 400
        assert "own admin privileges" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_cannot_deactivate_yourself(self, client, admin_headers, admin_user):
        """Admin should not be able to deactivate their own account."""
        response = await client.put(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_headers,
            json={"is_active": False},
        )

        assert response.status_code == 400
        assert "own account" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_can_update_own_name(self, client, admin_headers, admin_user):
        """Admin should still be able to update their own name."""
        response = await client.put(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_headers,
            json={"first_name": "UpdatedAdmin"},
        )

        assert response.status_code == 200
        assert response.json()["user"]["first_name"] == "UpdatedAdmin"

    @pytest.mark.asyncio
    async def test_update_nonexistent_user(self, client, admin_headers):
        """Should return 404 for non-existent user."""
        response = await client.put(
            "/api/admin/users/999999",
            headers=admin_headers,
            json={"first_name": "Ghost"},
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_non_admin_rejected(self, client, non_admin_headers, target_user):
        """Non-admin should be rejected."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=non_admin_headers,
            json={"first_name": "Hacker"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_user_no_auth(self, client, target_user):
        """Unauthenticated request should be rejected."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            json={"first_name": "NoAuth"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_partial_fields(self, client, admin_headers, target_user):
        """Should only update fields that are provided."""
        original_email = target_user.email
        original_last = target_user.last_name

        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={"first_name": "OnlyFirst"},
        )

        assert response.status_code == 200
        user = response.json()["user"]
        assert user["first_name"] == "OnlyFirst"
        assert user["email"] == original_email
        assert user["last_name"] == original_last


# =============================================================================
# Delete User Tests
# =============================================================================

class TestDeleteUser:
    """Tests for DELETE /api/admin/users/{user_id}."""

    @pytest.mark.asyncio
    async def test_delete_user_success(self, client, admin_headers, db_session):
        """Should delete a user."""
        from db_models import User
        unique = uuid.uuid4().hex[:8]
        user = User(
            email=f"todelete-{unique}@tagparking.co.uk",
            first_name="Delete",
            last_name="Me",
            is_admin=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        user_id = user.id

        response = await client.delete(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "deleted" in data["message"]

        # Verify user no longer exists
        deleted = db_session.query(User).filter(User.id == user_id).first()
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_user_with_login_codes(self, client, admin_headers, db_session):
        """Should clean up login_codes before deleting user."""
        from db_models import User, LoginCode

        unique = uuid.uuid4().hex[:8]
        user = User(
            email=f"withcodes-{unique}@tagparking.co.uk",
            first_name="Has",
            last_name="Codes",
            is_admin=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Add some login codes
        for code in ["111111", "222222", "333333"]:
            lc = LoginCode(
                user_id=user.id,
                code=code,
                expires_at=datetime.utcnow() + timedelta(minutes=10),
                used=False,
            )
            db_session.add(lc)
        db_session.commit()

        # Verify codes exist
        codes_before = db_session.query(LoginCode).filter(LoginCode.user_id == user.id).count()
        assert codes_before == 3

        response = await client.delete(
            f"/api/admin/users/{user.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200

        # Verify codes cleaned up
        codes_after = db_session.query(LoginCode).filter(LoginCode.user_id == user.id).count()
        assert codes_after == 0

    @pytest.mark.asyncio
    async def test_delete_user_with_sessions(self, client, admin_headers, db_session):
        """Should clean up sessions before deleting user."""
        from db_models import User, Session as DbSession

        unique = uuid.uuid4().hex[:8]
        user = User(
            email=f"withsessions-{unique}@tagparking.co.uk",
            first_name="Has",
            last_name="Sessions",
            is_admin=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Add sessions
        for i in range(2):
            sess = DbSession(
                user_id=user.id,
                token=f"deltest_{unique}_{i}",
                expires_at=datetime.utcnow() + timedelta(hours=8),
            )
            db_session.add(sess)
        db_session.commit()

        sessions_before = db_session.query(DbSession).filter(DbSession.user_id == user.id).count()
        assert sessions_before == 2

        response = await client.delete(
            f"/api/admin/users/{user.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200

        sessions_after = db_session.query(DbSession).filter(DbSession.user_id == user.id).count()
        assert sessions_after == 0

    @pytest.mark.asyncio
    async def test_delete_user_nullifies_pricing_settings(self, client, admin_headers, db_session):
        """Should nullify pricing_settings.updated_by references."""
        from db_models import User, PricingSettings

        unique = uuid.uuid4().hex[:8]
        user = User(
            email=f"withpricing-{unique}@tagparking.co.uk",
            first_name="Has",
            last_name="Pricing",
            is_admin=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Check if pricing_settings exists and update its updated_by
        pricing = db_session.query(PricingSettings).first()
        if pricing:
            original_updated_by = pricing.updated_by
            pricing.updated_by = user.id
            db_session.commit()

            response = await client.delete(
                f"/api/admin/users/{user.id}",
                headers=admin_headers,
            )

            assert response.status_code == 200

            db_session.refresh(pricing)
            assert pricing.updated_by is None

            # Restore original
            pricing.updated_by = original_updated_by
            db_session.commit()
        else:
            # No pricing settings — just delete user normally
            response = await client.delete(
                f"/api/admin/users/{user.id}",
                headers=admin_headers,
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_delete_yourself(self, client, admin_headers, admin_user):
        """Admin should not be able to delete their own account."""
        response = await client.delete(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_headers,
        )

        assert response.status_code == 400
        assert "own account" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, client, admin_headers):
        """Should return 404 for non-existent user."""
        response = await client.delete(
            "/api/admin/users/999999",
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_user_non_admin_rejected(self, client, non_admin_headers, target_user):
        """Non-admin should be rejected."""
        response = await client.delete(
            f"/api/admin/users/{target_user.id}",
            headers=non_admin_headers,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_user_no_auth(self, client, target_user):
        """Unauthenticated request should be rejected."""
        response = await client.delete(
            f"/api/admin/users/{target_user.id}",
        )

        assert response.status_code == 401


# =============================================================================
# Integration Tests — Full CRUD Lifecycle
# =============================================================================

class TestUserManagementIntegration:
    """End-to-end tests for the full user management workflow."""

    @pytest.mark.asyncio
    async def test_full_crud_lifecycle(self, client, admin_headers, db_session):
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
        unique = uuid.uuid4().hex[:8]
        email = f"lifecycle-{unique}@tagparking.co.uk"

        # 1. Create
        create_resp = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "first_name": "Lifecycle",
                "last_name": "Test",
                "phone": "+447000000001",
            },
        )
        assert create_resp.status_code == 200
        user_id = create_resp.json()["user"]["id"]
        assert create_resp.json()["user"]["is_admin"] is False

        # 2. Verify in list
        list_resp = await client.get("/api/admin/users", headers=admin_headers)
        emails = [u["email"] for u in list_resp.json()["users"]]
        assert email in emails

        # 3. Update name + promote
        update_resp = await client.put(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
            json={
                "first_name": "Updated",
                "last_name": "Lifecycle",
                "is_admin": True,
            },
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["user"]["first_name"] == "Updated"
        assert update_resp.json()["user"]["is_admin"] is True

        # 4. Verify update persisted in list
        list_resp2 = await client.get("/api/admin/users", headers=admin_headers)
        user_in_list = next(u for u in list_resp2.json()["users"] if u["id"] == user_id)
        assert user_in_list["first_name"] == "Updated"
        assert user_in_list["is_admin"] is True

        # 5. Deactivate
        deact_resp = await client.put(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert deact_resp.status_code == 200
        assert deact_resp.json()["user"]["is_active"] is False

        # 6. Reactivate
        react_resp = await client.put(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
            json={"is_active": True},
        )
        assert react_resp.status_code == 200
        assert react_resp.json()["user"]["is_active"] is True

        # 7. Delete
        delete_resp = await client.delete(
            f"/api/admin/users/{user_id}",
            headers=admin_headers,
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["success"] is True

        # 8. Verify gone
        list_resp3 = await client.get("/api/admin/users", headers=admin_headers)
        ids = [u["id"] for u in list_resp3.json()["users"]]
        assert user_id not in ids

    @pytest.mark.asyncio
    async def test_delete_user_with_login_history(self, client, admin_headers, db_session):
        """
        Simulate a real-world scenario: user has logged in (has login_codes
        and sessions), then is deleted by admin. FK cleanup must work.
        """
        from db_models import User, LoginCode, Session as DbSession

        unique = uuid.uuid4().hex[:8]
        user = User(
            email=f"loginhistory-{unique}@tagparking.co.uk",
            first_name="Login",
            last_name="History",
            is_admin=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        # Simulate login history
        lc = LoginCode(
            user_id=user.id,
            code="888888",
            expires_at=datetime.utcnow() - timedelta(minutes=5),
            used=True,
        )
        db_session.add(lc)

        sess = DbSession(
            user_id=user.id,
            token=f"history_{unique}",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(sess)
        db_session.commit()

        # Delete should succeed (FK cleanup)
        response = await client.delete(
            f"/api/admin/users/{user.id}",
            headers=admin_headers,
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify fully cleaned up
        assert db_session.query(User).filter(User.id == user.id).first() is None
        assert db_session.query(LoginCode).filter(LoginCode.user_id == user.id).count() == 0
        assert db_session.query(DbSession).filter(DbSession.user_id == user.id).count() == 0

    @pytest.mark.asyncio
    async def test_non_admin_cannot_perform_any_crud(self, client, non_admin_headers, target_user, db_session):
        """Non-admin should get 403 on all user management endpoints."""
        unique = uuid.uuid4().hex[:8]

        # Create
        create_resp = await client.post(
            "/api/admin/users",
            headers=non_admin_headers,
            json={"email": f"fail-{unique}@test.com", "first_name": "F", "last_name": "F"},
        )
        assert create_resp.status_code == 403

        # List
        list_resp = await client.get("/api/admin/users", headers=non_admin_headers)
        assert list_resp.status_code == 403

        # Update
        update_resp = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=non_admin_headers,
            json={"first_name": "Hacked"},
        )
        assert update_resp.status_code == 403

        # Delete
        delete_resp = await client.delete(
            f"/api/admin/users/{target_user.id}",
            headers=non_admin_headers,
        )
        assert delete_resp.status_code == 403


# =============================================================================
# Edge Cases
# =============================================================================

class TestUserManagementEdgeCases:
    """Edge case and security tests."""

    @pytest.mark.asyncio
    async def test_create_user_empty_email(self, client, admin_headers, db_session):
        """Empty email is accepted by the endpoint (no server-side validation)."""
        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": "",
                "first_name": "Empty",
                "last_name": "Email",
            },
        )

        # Currently accepted — endpoint does .strip().lower() but no empty check
        # Second call with empty email should fail as duplicate
        if response.status_code == 200:
            from db_models import User
            created = db_session.query(User).filter(User.email == "").first()
            if created:
                db_session.delete(created)
                db_session.commit()

            response2 = await client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "email": "",
                    "first_name": "Dup",
                    "last_name": "Empty",
                },
            )
            assert response2.status_code == 400
            assert "already exists" in response2.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_user_empty_body(self, client, admin_headers, target_user):
        """Should handle empty update body (no changes)."""
        response = await client.put(
            f"/api/admin/users/{target_user.id}",
            headers=admin_headers,
            json={},
        )

        # Should succeed — nothing to update
        assert response.status_code == 200
        assert response.json()["user"]["id"] == target_user.id

    @pytest.mark.asyncio
    async def test_special_characters_in_name(self, client, admin_headers, db_session):
        """Should handle names with special characters."""
        unique = uuid.uuid4().hex[:8]
        email = f"special-{unique}@tagparking.co.uk"

        response = await client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "email": email,
                "first_name": "O'Brien",
                "last_name": "Müller-Schmidt",
            },
        )

        assert response.status_code == 200
        assert response.json()["user"]["first_name"] == "O'Brien"
        assert response.json()["user"]["last_name"] == "Müller-Schmidt"

        from db_models import User
        created = db_session.query(User).filter(User.email == email).first()
        if created:
            db_session.delete(created)
            db_session.commit()

    @pytest.mark.asyncio
    async def test_expired_admin_session_rejected(self, client, db_session, admin_user):
        """Should reject expired admin session."""
        from db_models import Session as DbSession
        expired = DbSession(
            user_id=admin_user.id,
            token=f"expired_admin_{uuid.uuid4().hex}",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        db_session.add(expired)
        db_session.commit()

        response = await client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {expired.token}"},
        )

        assert response.status_code == 401

        db_session.delete(expired)
        db_session.commit()
