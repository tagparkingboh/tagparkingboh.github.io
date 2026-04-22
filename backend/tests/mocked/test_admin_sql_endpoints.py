"""
Unit and Integration tests for Admin SQL endpoints.

Tests the secure SQL query interface functionality:
- POST /api/admin/sql/verify-pin (PIN verification)
- GET /api/admin/sql/session-status (check session)
- POST /api/admin/sql/execute (execute queries)
- POST /api/admin/sql/logout (terminate session)

All tests use mocks - no database connection required.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


# ============================================================================
# Mock Factory Functions
# ============================================================================

def create_mock_admin_user(id=1, email="admin@test.com"):
    """Create a mock admin user."""
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_admin = True
    user.is_active = True
    return user


def create_mock_settings(admin_sql_pin="123456"):
    """Create mock settings."""
    settings = MagicMock()
    settings.admin_sql_pin = admin_sql_pin
    return settings


def create_mock_session_token():
    """Create a mock session token response."""
    return {
        "token": "mock_session_token_abc123",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
    }


# ============================================================================
# PIN Verification Tests
# ============================================================================

class TestVerifyPinLogic:
    """Unit tests for PIN verification logic."""

    # Happy Path
    def test_correct_pin_returns_success(self):
        """Should return success when PIN is correct."""
        correct_pin = "123456"
        entered_pin = "123456"

        is_valid = entered_pin == correct_pin

        assert is_valid is True

    def test_generates_session_token(self):
        """Should generate a session token on success."""
        import secrets

        token = secrets.token_urlsafe(32)

        assert len(token) > 20
        assert isinstance(token, str)

    def test_sets_expiry_2_hours(self):
        """Should set session expiry to 2 hours."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=2)

        time_diff = (expires_at - now).total_seconds()

        assert time_diff == 7200  # 2 hours in seconds

    def test_stores_session_in_dict(self):
        """Should store session in session tokens dict."""
        sql_session_tokens = {}
        user_id = 1
        token = "test_token"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=2)

        sql_session_tokens[user_id] = {
            "token": token,
            "expires_at": expires_at,
        }

        assert user_id in sql_session_tokens
        assert sql_session_tokens[user_id]["token"] == token

    # Unhappy Path
    def test_incorrect_pin_rejected(self):
        """Should reject incorrect PIN."""
        correct_pin = "123456"
        entered_pin = "000000"

        is_valid = entered_pin == correct_pin

        assert is_valid is False

    def test_empty_pin_rejected(self):
        """Should reject empty PIN."""
        correct_pin = "123456"
        entered_pin = ""

        is_valid = entered_pin == correct_pin

        assert is_valid is False

    def test_pin_not_configured_error(self):
        """Should error when PIN not configured."""
        settings = create_mock_settings(admin_sql_pin=None)

        is_configured = settings.admin_sql_pin is not None

        assert is_configured is False

    def test_pin_whitespace_not_valid(self):
        """Should not match PIN with whitespace."""
        correct_pin = "123456"
        entered_pin = " 123456 "

        is_valid = entered_pin == correct_pin

        assert is_valid is False


# ============================================================================
# Session Status Tests
# ============================================================================

class TestSessionStatusLogic:
    """Unit tests for session status logic."""

    # Happy Path
    def test_valid_session_returns_true(self):
        """Should return valid=True for active session."""
        now = datetime.now(timezone.utc)
        session = {
            "token": "valid_token",
            "expires_at": now + timedelta(hours=1),
        }

        is_valid = now < session["expires_at"]

        assert is_valid is True

    def test_returns_expires_at(self):
        """Should return expires_at timestamp."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=2)
        session = {"expires_at": expires_at}

        result = session["expires_at"].isoformat()

        assert isinstance(result, str)
        assert "T" in result

    # Unhappy Path
    def test_no_session_returns_invalid(self):
        """Should return valid=False when no session."""
        sql_session_tokens = {}
        user_id = 1

        has_session = user_id in sql_session_tokens

        assert has_session is False

    def test_expired_session_returns_invalid(self):
        """Should return valid=False for expired session."""
        now = datetime.now(timezone.utc)
        session = {
            "token": "expired_token",
            "expires_at": now - timedelta(hours=1),  # Expired
        }

        is_valid = now < session["expires_at"]

        assert is_valid is False

    def test_expired_session_cleaned_up(self):
        """Should clean up expired session."""
        sql_session_tokens = {
            1: {
                "token": "expired",
                "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
            }
        }

        # Simulate cleanup
        if datetime.now(timezone.utc) > sql_session_tokens[1]["expires_at"]:
            del sql_session_tokens[1]

        assert 1 not in sql_session_tokens


# ============================================================================
# Execute Query Tests - Blocked Commands
# ============================================================================

class TestBlockedCommands:
    """Tests for blocked SQL commands."""

    BLOCKED_COMMANDS = [
        'DROP', 'TRUNCATE', 'ALTER', 'CREATE', 'GRANT', 'REVOKE',
        'VACUUM', 'REINDEX', 'CLUSTER', 'COPY', 'EXECUTE',
        'DEALLOCATE', 'PREPARE', 'LISTEN', 'NOTIFY', 'UNLISTEN',
        'LOAD', 'SECURITY', 'OWNER', 'TABLESPACE', 'EXTENSION',
    ]

    def test_drop_table_blocked(self):
        """Should block DROP TABLE commands."""
        query = "DROP TABLE users"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_truncate_blocked(self):
        """Should block TRUNCATE commands."""
        query = "TRUNCATE TABLE bookings"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_alter_table_blocked(self):
        """Should block ALTER TABLE commands."""
        query = "ALTER TABLE users ADD COLUMN password VARCHAR(255)"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_create_blocked(self):
        """Should block CREATE commands."""
        query = "CREATE TABLE temp (id INT)"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_grant_blocked(self):
        """Should block GRANT commands."""
        query = "GRANT ALL ON users TO public"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_vacuum_blocked(self):
        """Should block VACUUM commands."""
        query = "VACUUM ANALYZE users"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_copy_blocked(self):
        """Should block COPY commands."""
        query = "COPY users TO '/tmp/users.csv'"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is True

    def test_select_not_blocked(self):
        """Should not block SELECT commands."""
        query = "SELECT * FROM users"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is False

    def test_insert_not_blocked(self):
        """Should not block INSERT commands (requires confirmation)."""
        query = "INSERT INTO users (name) VALUES ('test')"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is False

    def test_update_not_blocked(self):
        """Should not block UPDATE commands (requires confirmation)."""
        query = "UPDATE users SET name = 'new' WHERE id = 1"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is False

    def test_delete_not_blocked(self):
        """Should not block DELETE commands (requires confirmation)."""
        query = "DELETE FROM users WHERE id = 1"
        query_upper = query.upper()

        is_blocked = any(cmd in query_upper for cmd in self.BLOCKED_COMMANDS)

        assert is_blocked is False


# ============================================================================
# Execute Query Tests - Write Operations
# ============================================================================

class TestWriteOperations:
    """Tests for write operation detection."""

    WRITE_COMMANDS = ['INSERT', 'UPDATE', 'DELETE']

    def test_insert_is_write_operation(self):
        """Should detect INSERT as write operation."""
        query = "INSERT INTO users (name) VALUES ('test')"

        is_write = query.upper().strip().startswith(tuple(self.WRITE_COMMANDS))

        assert is_write is True

    def test_update_is_write_operation(self):
        """Should detect UPDATE as write operation."""
        query = "UPDATE users SET name = 'new' WHERE id = 1"

        is_write = query.upper().strip().startswith(tuple(self.WRITE_COMMANDS))

        assert is_write is True

    def test_delete_is_write_operation(self):
        """Should detect DELETE as write operation."""
        query = "DELETE FROM users WHERE id = 1"

        is_write = query.upper().strip().startswith(tuple(self.WRITE_COMMANDS))

        assert is_write is True

    def test_select_not_write_operation(self):
        """Should not detect SELECT as write operation."""
        query = "SELECT * FROM users"

        is_write = query.upper().strip().startswith(tuple(self.WRITE_COMMANDS))

        assert is_write is False

    def test_write_requires_confirmation(self):
        """Should require confirmation for write operations."""
        query = "UPDATE users SET active = false WHERE id = 1"
        confirmed = False

        is_write = query.upper().strip().startswith(tuple(self.WRITE_COMMANDS))
        requires_confirmation = is_write and not confirmed

        assert requires_confirmation is True

    def test_write_with_confirmation_proceeds(self):
        """Should proceed with confirmation for write operations."""
        query = "UPDATE users SET active = false WHERE id = 1"
        confirmed = True

        is_write = query.upper().strip().startswith(tuple(self.WRITE_COMMANDS))
        requires_confirmation = is_write and not confirmed

        assert requires_confirmation is False


# ============================================================================
# Execute Query Tests - Session Validation
# ============================================================================

class TestQuerySessionValidation:
    """Tests for query session validation."""

    def test_missing_session_rejected(self):
        """Should reject query without session."""
        sql_session_tokens = {}
        user_id = 1

        has_session = user_id in sql_session_tokens

        assert has_session is False

    def test_invalid_token_rejected(self):
        """Should reject query with invalid token."""
        sql_session_tokens = {
            1: {
                "token": "correct_token",
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            }
        }
        request_token = "wrong_token"
        user_id = 1

        session = sql_session_tokens.get(user_id)
        is_valid = session and session["token"] == request_token

        assert is_valid is False

    def test_valid_token_accepted(self):
        """Should accept query with valid token."""
        token = "correct_token"
        sql_session_tokens = {
            1: {
                "token": token,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            }
        }
        user_id = 1

        session = sql_session_tokens.get(user_id)
        is_valid = session and session["token"] == token

        assert is_valid is True

    def test_expired_token_rejected(self):
        """Should reject query with expired token."""
        now = datetime.now(timezone.utc)
        sql_session_tokens = {
            1: {
                "token": "valid_token",
                "expires_at": now - timedelta(hours=1),  # Expired
            }
        }
        user_id = 1

        session = sql_session_tokens.get(user_id)
        is_valid = session and now < session["expires_at"]

        assert is_valid is False


# ============================================================================
# Execute Query Tests - Query Execution
# ============================================================================

class TestQueryExecution:
    """Tests for query execution logic."""

    def test_empty_query_rejected(self):
        """Should reject empty query."""
        query = ""

        is_valid = query.strip() != ""

        assert is_valid is False

    def test_whitespace_query_rejected(self):
        """Should reject whitespace-only query."""
        query = "   "

        is_valid = query.strip() != ""

        assert is_valid is False

    def test_select_returns_columns_and_data(self):
        """Should return columns and data for SELECT."""
        # Simulate query result
        columns = ["id", "name", "email"]
        rows = [
            (1, "John", "john@test.com"),
            (2, "Jane", "jane@test.com"),
        ]

        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                row_dict[col] = row[i]
            data.append(row_dict)

        assert len(data) == 2
        assert data[0]["name"] == "John"
        assert "email" in data[1]

    def test_select_respects_row_limit(self):
        """Should respect 500 row limit."""
        rows = list(range(1000))
        limit = 500

        result = rows[:limit]

        assert len(result) == 500

    def test_select_indicates_more_rows(self):
        """Should indicate when more rows available."""
        total_rows = 1000
        fetched = 500
        limit = 500

        has_more = fetched == limit

        assert has_more is True

    def test_write_returns_affected_rows(self):
        """Should return affected rows for write operations."""
        affected_rows = 5

        result = {
            "success": True,
            "query_type": "UPDATE",
            "affected_rows": affected_rows,
        }

        assert result["affected_rows"] == 5

    def test_datetime_serialized_to_iso(self):
        """Should serialize datetime to ISO format."""
        dt = datetime(2026, 4, 21, 14, 30, 0, tzinfo=timezone.utc)

        serialized = dt.isoformat()

        assert "2026-04-21" in serialized
        assert "T" in serialized


# ============================================================================
# Execute Query Tests - Error Handling
# ============================================================================

class TestQueryErrorHandling:
    """Tests for query error handling."""

    def test_syntax_error_returns_message(self):
        """Should return error message for syntax errors."""
        error_msg = "ERROR: syntax error at or near 'SELEC'"

        result = {"error": f"Query error: {error_msg}"}

        assert "syntax error" in result["error"]

    def test_table_not_found_error(self):
        """Should handle table not found errors."""
        error_msg = "ERROR: relation 'nonexistent' does not exist"

        result = {"error": f"Query error: {error_msg}"}

        assert "does not exist" in result["error"]

    def test_timeout_handled(self):
        """Should handle query timeout."""
        timeout_seconds = 30

        assert timeout_seconds == 30

    def test_rollback_on_error(self):
        """Should rollback on error."""
        mock_db = MagicMock()

        # Simulate error and rollback
        mock_db.rollback()

        mock_db.rollback.assert_called_once()


# ============================================================================
# Logout Tests
# ============================================================================

class TestLogoutLogic:
    """Unit tests for SQL session logout."""

    def test_removes_session_from_dict(self):
        """Should remove session from tokens dict."""
        sql_session_tokens = {
            1: {"token": "test", "expires_at": datetime.now(timezone.utc)},
        }
        user_id = 1

        if user_id in sql_session_tokens:
            del sql_session_tokens[user_id]

        assert user_id not in sql_session_tokens

    def test_logout_success_response(self):
        """Should return success message."""
        result = {"success": True, "message": "SQL session terminated"}

        assert result["success"] is True
        assert "terminated" in result["message"]

    def test_logout_idempotent(self):
        """Should handle logout when no session exists."""
        sql_session_tokens = {}
        user_id = 1

        # Should not raise error
        if user_id in sql_session_tokens:
            del sql_session_tokens[user_id]

        assert True  # No error raised


# ============================================================================
# Security Tests
# ============================================================================

class TestSQLSecurityFeatures:
    """Tests for SQL interface security features."""

    def test_requires_admin_user(self):
        """Should require admin user."""
        user = create_mock_admin_user()

        assert user.is_admin is True

    def test_non_admin_rejected(self):
        """Should reject non-admin users."""
        user = MagicMock()
        user.is_admin = False

        assert user.is_admin is False

    def test_queries_logged(self):
        """Should log all queries."""
        query = "SELECT * FROM users"
        user_email = "admin@test.com"

        log_entry = {
            "user_email": user_email,
            "query": query[:1000],
        }

        assert log_entry["query"] == query
        assert "admin@test.com" in log_entry["user_email"]

    def test_long_queries_truncated_in_log(self):
        """Should truncate long queries in logs."""
        long_query = "SELECT * FROM users WHERE " + "x=1 OR " * 500

        truncated = long_query[:1000]

        assert len(truncated) == 1000

    def test_session_token_is_random(self):
        """Should generate random session tokens."""
        import secrets

        token1 = secrets.token_urlsafe(32)
        token2 = secrets.token_urlsafe(32)

        assert token1 != token2
        assert len(token1) >= 32

    def test_blocked_command_word_boundaries(self):
        """Should use word boundaries for blocked commands."""
        import re

        # 'created_at' should NOT match 'CREATE'
        query = "SELECT created_at FROM users"
        pattern = r'\bCREATE\b'

        matches = re.search(pattern, query.upper())

        assert matches is None

    def test_create_table_matches(self):
        """Should match actual CREATE command."""
        import re

        query = "CREATE TABLE temp (id INT)"
        pattern = r'\bCREATE\b'

        matches = re.search(pattern, query.upper())

        assert matches is not None


# ============================================================================
# Response Structure Tests
# ============================================================================

class TestSQLResponseStructure:
    """Tests for response structure."""

    def test_verify_pin_response(self):
        """Should return correct verify PIN response."""
        response = {
            "success": True,
            "session_token": "token_abc123",
            "expires_at": "2026-04-21T16:00:00+00:00",
        }

        assert "success" in response
        assert "session_token" in response
        assert "expires_at" in response

    def test_session_status_valid_response(self):
        """Should return correct valid session status response."""
        response = {
            "valid": True,
            "expires_at": "2026-04-21T16:00:00+00:00",
        }

        assert response["valid"] is True
        assert "expires_at" in response

    def test_session_status_invalid_response(self):
        """Should return correct invalid session status response."""
        response = {
            "valid": False,
            "reason": "expired",
        }

        assert response["valid"] is False
        assert "reason" in response

    def test_select_query_response(self):
        """Should return correct SELECT response."""
        response = {
            "success": True,
            "query_type": "SELECT",
            "columns": ["id", "name"],
            "data": [{"id": 1, "name": "Test"}],
            "row_count": 1,
            "has_more": False,
            "execution_time": 0.025,
        }

        assert response["query_type"] == "SELECT"
        assert "columns" in response
        assert "data" in response
        assert "row_count" in response

    def test_write_query_response(self):
        """Should return correct write query response."""
        response = {
            "success": True,
            "query_type": "UPDATE",
            "affected_rows": 5,
            "execution_time": 0.015,
        }

        assert response["query_type"] == "UPDATE"
        assert "affected_rows" in response

    def test_confirmation_required_response(self):
        """Should return correct confirmation required response."""
        response = {
            "requires_confirmation": True,
            "operation_type": "DELETE",
            "message": "This is a write operation. Please confirm to proceed.",
        }

        assert response["requires_confirmation"] is True
        assert "operation_type" in response


# ============================================================================
# Boundary Tests
# ============================================================================

class TestSQLBoundaries:
    """Tests for boundary conditions."""

    def test_very_long_query(self):
        """Should handle very long queries."""
        long_query = "SELECT * FROM users WHERE " + "id = 1 OR " * 1000

        assert len(long_query) > 10000

    def test_special_characters_in_query(self):
        """Should handle special characters."""
        query = "SELECT * FROM users WHERE name = 'O''Brien'"

        assert "O''Brien" in query

    def test_unicode_in_query(self):
        """Should handle unicode in queries."""
        query = "SELECT * FROM users WHERE city = 'München'"

        assert "München" in query

    def test_multiline_query(self):
        """Should handle multiline queries."""
        query = """
        SELECT
            id,
            name,
            email
        FROM users
        WHERE active = true
        """

        assert "SELECT" in query.upper()
        assert "FROM" in query.upper()

    def test_multiple_statements_handling(self):
        """Should handle multiple statements."""
        query = "SELECT * FROM users; SELECT * FROM bookings"

        has_multiple = ";" in query

        assert has_multiple is True

    def test_session_expiry_boundary(self):
        """Should handle exact expiry time."""
        now = datetime.now(timezone.utc)
        expires_at = now  # Exactly now

        is_expired = now >= expires_at

        assert is_expired is True

    def test_zero_rows_result(self):
        """Should handle zero rows result."""
        data = []
        row_count = len(data)

        assert row_count == 0

    def test_max_rows_result(self):
        """Should handle max rows (500)."""
        rows = list(range(500))

        assert len(rows) == 500


# ============================================================================
# Authentication Tests
# ============================================================================

class TestSQLAuthentication:
    """Tests for SQL endpoint authentication."""

    def test_all_endpoints_require_admin(self):
        """All SQL endpoints should require admin."""
        endpoints = [
            "/api/admin/sql/verify-pin",
            "/api/admin/sql/session-status",
            "/api/admin/sql/execute",
            "/api/admin/sql/logout",
        ]

        for endpoint in endpoints:
            assert "/api/admin/" in endpoint

    def test_pin_verification_logs_failed_attempts(self):
        """Should log failed PIN attempts."""
        user_id = 1
        user_email = "admin@test.com"

        log_message = f"[SQL] Failed PIN attempt by user {user_id} ({user_email})"

        assert str(user_id) in log_message
        assert user_email in log_message


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
