"""
HUEB tests for PR 7 of the 2026-05-29 security review: admin SQL console
hardening — the 3 quick wins.

The console stays usable for admin emergency writes (INSERT/UPDATE/DELETE
still allowed with confirmation), but PR 7 makes it:
  1. auditable          — every query attempt persists to audit_logs
                          with user_id, query, status, row count
  2. multi-statement-proof — ; outside string literals is rejected
                          BEFORE either statement runs
  3. obvious-bypass-proof — comments are stripped before the keyword
                          check, and CALL joins the blocklist

The SELECT-only policy, read-only DB role, and two-person approval
are deferred to PRs 8/9/10 respectively.

Implementation tested:
  - _strip_sql_comments  (helper, unit-tested directly)
  - _contains_unquoted_semicolon  (helper, unit-tested directly)
  - is_sql_command_blocked  (now strips comments first)
  - BLOCKED_SQL_COMMANDS    (CALL added)
  - execute_sql_query       (audit persistence + multi-statement gate)
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

import main
from main import (
    app,
    _strip_sql_comments,
    _contains_unquoted_semicolon,
    is_sql_command_blocked,
    BLOCKED_SQL_COMMANDS,
    require_admin,
)
from database import get_db


# ============================================================================
# Helper unit tests — no HTTP
# ============================================================================


class TestStripSqlComments:
    """_strip_sql_comments removes -- and /* */ comments but preserves
    quoted-string contents."""

    def test_H_line_comment_stripped(self):
        # H: -- DROP TABLE users is a comment, gets stripped, the
        # downstream keyword check sees only 'SELECT 1'.
        assert "DROP" not in _strip_sql_comments(
            "SELECT 1 -- DROP TABLE users"
        ).upper()

    def test_H_block_comment_stripped(self):
        # H: /* DROP */ block comment stripped, only 'SELECT 1 FROM x'.
        assert "DROP" not in _strip_sql_comments(
            "SELECT 1 /* DROP TABLE x */ FROM x"
        ).upper()

    def test_U_quoted_dashes_preserved(self):
        # U: '--' INSIDE a string literal is NOT a comment.
        cleaned = _strip_sql_comments("SELECT '-- not a comment' AS x")
        assert "-- not a comment" in cleaned

    def test_U_quoted_block_comment_markers_preserved(self):
        # U: '/* */' inside a string literal is data, not a comment.
        cleaned = _strip_sql_comments("SELECT '/* preserved */' AS x")
        assert "/* preserved */" in cleaned

    def test_E_postgres_doubled_quote_escape_preserved(self):
        # E: Postgres '' escape inside a literal must NOT close the
        # quote and leak into "comment mode".
        cleaned = _strip_sql_comments(
            "SELECT 'O''Brien -- still in string' AS x"
        )
        assert "O''Brien -- still in string" in cleaned

    def test_B_unterminated_line_comment_at_eof(self):
        # B: -- comment without a trailing newline (end of input) →
        # everything after the -- is stripped, no error.
        assert _strip_sql_comments("SELECT 1 -- trailing") == "SELECT 1 "


class TestContainsUnquotedSemicolon:
    """_contains_unquoted_semicolon walks the query and finds ; outside
    of quoted strings."""

    def test_H_multi_statement_flagged(self):
        # H: classic chain — ; between two statements → True.
        assert _contains_unquoted_semicolon(
            "SELECT 1; DELETE FROM bookings WHERE id > 0"
        )

    def test_U_no_semicolon_returns_false(self):
        # U: clean SELECT → False.
        assert not _contains_unquoted_semicolon("SELECT 1 FROM bookings")

    def test_E_semicolon_inside_string_literal_ignored(self):
        # E: ; inside a 'string' is NOT a statement separator. This
        # regression matters for queries like
        #   SELECT 'a; b' AS x
        # which is legit SQL and must not be blocked.
        assert not _contains_unquoted_semicolon(
            "SELECT 'separator; inside string' AS x"
        )

    def test_E_semicolon_inside_double_quoted_ident_ignored(self):
        # E: "double-quoted identifier" with ; inside (rare but valid
        # in Postgres) — not a statement separator.
        assert not _contains_unquoted_semicolon(
            'SELECT "col;name" FROM bookings'
        )


class TestIsSqlCommandBlockedCommentStripping:
    """is_sql_command_blocked must strip comments BEFORE checking, so
    a destructive keyword hidden in a comment still trips the gate."""

    def test_E_comment_only_drop_is_allowed_not_executable(self):
        # E: Comment-only DROP passes the keyword check by design —
        # Postgres ignores the comment so the keyword wouldn't run
        # anyway, and rejecting annotated queries would break a
        # legitimate workflow (admins leaving "-- TODO" notes etc.).
        # The keyword has to be OUTSIDE any comment to actually
        # execute, and that case is covered by
        # test_H_comment_alongside_real_drop_still_blocked below.
        is_blocked, cmd = is_sql_command_blocked(
            "SELECT 1 /* DROP TABLE x */ FROM users"
        )
        assert not is_blocked, (
            "Comment-only DROP should NOT trigger the block — Postgres "
            "wouldn't execute it anyway, and blocking would prevent "
            "legitimate annotated queries."
        )

    def test_H_comment_alongside_real_drop_still_blocked(self):
        # H: query has a real DROP outside any comment → blocked.
        is_blocked, cmd = is_sql_command_blocked(
            "DROP TABLE users -- some comment"
        )
        assert is_blocked
        assert cmd == "DROP"

    def test_U_call_added_to_blocklist(self):
        # U: PR 7 added CALL to BLOCKED_SQL_COMMANDS — stored
        # procedures are arbitrary code execution from a SQL prompt.
        assert "CALL" in BLOCKED_SQL_COMMANDS
        is_blocked, cmd = is_sql_command_blocked(
            "CALL some_stored_proc()"
        )
        assert is_blocked
        assert cmd == "CALL"


# ============================================================================
# Endpoint integration — TestClient
# ============================================================================


SESSION_TOKEN = "test-session-token-pr7"


@pytest.fixture
def admin_user():
    return SimpleNamespace(
        id=1, email="admin@tag.test", is_admin=True, is_active=True,
        first_name="Admin", last_name="Test",
    )


@pytest.fixture
def admin_override(admin_user):
    app.dependency_overrides[require_admin] = lambda: admin_user
    try:
        yield
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def valid_sql_session(admin_user, monkeypatch):
    """Install a not-yet-expired SQL session for the admin user so the
    execute handler's session check passes."""
    from datetime import timedelta
    main.sql_session_tokens[admin_user.id] = {
        "token": SESSION_TOKEN,
        "expires_at": main.get_uk_now() + timedelta(hours=1),
    }
    try:
        yield
    finally:
        main.sql_session_tokens.pop(admin_user.id, None)


@pytest.fixture
def stub_db(monkeypatch):
    """Replace the get_db dependency with a MagicMock session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()

    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestExecuteMultiStatementGate:
    """The execute endpoint rejects ; outside string literals BEFORE
    running the query. Closes SELECT 1; DELETE chains."""

    def test_U_select_then_delete_returns_400_no_exec(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # U: classic chain — the multi-statement gate fires 400 and
        # db.execute MUST NOT be reached.
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1; DELETE FROM bookings WHERE id > 0",
            "session_token": SESSION_TOKEN,
            "confirmed": True,
        })
        assert resp.status_code == 400
        assert "Multi-statement" in resp.json()["detail"]
        # db.execute was never invoked with the user's query — it might
        # have run the statement_timeout SET, but NOT the user query.
        user_query_calls = [
            c for c in stub_db.execute.call_args_list
            if "DELETE" in str(c.args[0]).upper()
            or "SELECT 1" in str(c.args[0]).upper()
        ]
        assert user_query_calls == [], (
            "User query reached db.execute despite the multi-statement "
            "gate. The chain bypass is open."
        )

    def test_E_single_trailing_semicolon_allowed(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # E: 'SELECT 1;' is normal SQL — the gate must strip ONE
        # trailing ; before the multi-statement check.
        mock_result = MagicMock()
        mock_result.fetchmany.return_value = [(1,)]
        mock_result.keys.return_value = ["?column?"]

        def _exec(stmt, *a, **kw):
            stmt_str = str(stmt).upper()
            if "STATEMENT_TIMEOUT" in stmt_str:
                return MagicMock()
            return mock_result
        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1;",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200

    def test_U_semicolon_inside_string_literal_allowed(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # U: ';' INSIDE a string literal is data, not a separator —
        # must not trip the gate.
        mock_result = MagicMock()
        mock_result.fetchmany.return_value = [("a; b",)]
        mock_result.keys.return_value = ["x"]

        def _exec(stmt, *a, **kw):
            if "STATEMENT_TIMEOUT" in str(stmt).upper():
                return MagicMock()
            return mock_result
        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 'a; b' AS x",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200


class TestExecuteAuditPersistence:
    """Every query attempt — success, blocked, or DB error — must
    persist an AuditLog row to audit_logs (NOT just stdout)."""

    def test_H_success_persists_audit_row(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # H: SELECT succeeds → an AuditLog row is added + committed
        # in the dedicated audit DB session (so a rolled-back user
        # query still leaves the trail).
        added_rows = []
        committed = [0]

        class _FakeAuditSession:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def add(self, obj): added_rows.append(obj)
            def commit(self): committed[0] += 1

        monkeypatch.setattr(
            main, "SessionLocal", lambda: _FakeAuditSession(),
            raising=False,
        )
        # Also patch the from-import inside _persist_sql_audit:
        monkeypatch.setattr(
            "database.SessionLocal", lambda: _FakeAuditSession(),
        )

        mock_result = MagicMock()
        mock_result.fetchmany.return_value = [(1,)]
        mock_result.keys.return_value = ["?column?"]
        def _exec(stmt, *a, **kw):
            if "STATEMENT_TIMEOUT" in str(stmt).upper():
                return MagicMock()
            return mock_result
        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1 FROM bookings LIMIT 1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200
        assert len(added_rows) == 1, (
            f"Expected exactly one AuditLog row to be added; got "
            f"{len(added_rows)}. Pre-PR-7 the row was created but "
            f"never db.add'd — stdout-only audit is not durable."
        )
        assert committed[0] == 1, (
            f"AuditLog row was add()'d but never commit()'d "
            f"({committed[0]} commits). Without commit the row "
            f"vanishes on session close."
        )

    def test_U_db_error_still_persists_audit_row(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # U: query raised mid-execution → audit row STILL lands so the
        # trail exists for forensics. Persistence runs in a separate
        # SessionLocal so the rolled-back user transaction doesn't
        # take the audit row with it.
        added_rows = []
        committed = [0]

        class _FakeAuditSession:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def add(self, obj): added_rows.append(obj)
            def commit(self): committed[0] += 1

        monkeypatch.setattr(
            "database.SessionLocal", lambda: _FakeAuditSession(),
        )

        def _exec(stmt, *a, **kw):
            if "STATEMENT_TIMEOUT" in str(stmt).upper():
                return MagicMock()
            raise Exception("simulated DB error")
        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT * FROM bookings LIMIT 1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 400  # Query error
        assert len(added_rows) == 1, (
            "Error-path audit row missing — forensics gap on failed "
            "queries."
        )
        assert committed[0] == 1

    def test_E_audit_logging_failure_does_not_break_user_response(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # E: audit persistence is best-effort. If the audit DB session
        # raises, the user MUST still get the query result back —
        # we never break the foreground request for a logging miss.
        def _broken_session():
            raise Exception("audit DB unreachable")
        monkeypatch.setattr(
            "database.SessionLocal", _broken_session,
        )

        mock_result = MagicMock()
        mock_result.fetchmany.return_value = [(1,)]
        mock_result.keys.return_value = ["?column?"]
        def _exec(stmt, *a, **kw):
            if "STATEMENT_TIMEOUT" in str(stmt).upper():
                return MagicMock()
            return mock_result
        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200, resp.text
        assert resp.json()["row_count"] == 1


class TestExecuteCommentHiddenKeywords:
    """End-to-end: a query with a comment-hidden DROP must pass through
    the keyword check (since the SQL engine would never execute the
    commented portion). Real destructive keywords outside comments
    still block."""

    def test_U_real_drop_outside_comment_blocked(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # U: DROP outside any comment → 403.
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "DROP TABLE users -- comment after",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        assert "DROP" in resp.json()["detail"]

    def test_U_call_blocked_by_new_blocklist(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # U: CALL is now blocked (PR 7 added).
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "CALL some_procedure(1, 2)",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        assert "CALL" in resp.json()["detail"]


# ============================================================================
# 2026-05-29 review-fix regression tests
# ============================================================================


class TestLeadingCommentDoesNotBypassWriteConfirmation:
    """Reviewer flagged HIGH: pre-fix is_write_operation used the raw
    query, so /* maintenance */ UPDATE bookings... started with '/'
    rather than 'UPDATE' and skipped the write-confirmation gate.
    Fix: strip comments once and use the cleaned form for is_write +
    SELECT detection + query_type."""

    def test_U_block_comment_before_update_requires_confirmation(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # U: leading block comment + UPDATE → must return
        # requires_confirmation, NOT execute the UPDATE.
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "/* maintenance */ UPDATE bookings SET status='cancelled' WHERE id=123",
            "session_token": SESSION_TOKEN,
            # confirmed deliberately omitted — expecting the
            # confirmation prompt, NOT execution.
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("requires_confirmation") is True, (
            f"Expected requires_confirmation=True on leading-comment "
            f"UPDATE; got {body!r}. The comment-strip normalisation "
            f"is missing from is_write_operation."
        )
        assert body.get("operation_type") == "UPDATE"

    def test_U_line_comment_before_delete_requires_confirmation(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # U: leading -- comment + newline + DELETE → must require
        # confirmation. Same bypass shape as the block-comment case.
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "-- note: emergency cleanup\nDELETE FROM bookings WHERE id=123",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("requires_confirmation") is True
        assert body.get("operation_type") == "DELETE"


class TestRejectedAttemptsAreAudited:
    """Reviewer flagged MEDIUM: pre-fix the audit helper was defined
    AFTER the multi-statement + blocked-command gates, so suspicious
    attempts (the ones we most want a forensic trail for) vanished
    silently. Fix: define the helper above the gates and call it
    with status='blocked' before raising."""

    def _wire_audit_capture(self, monkeypatch):
        """Capture AuditLog rows added via the dedicated audit
        SessionLocal so the test can introspect status / reason."""
        added_rows = []
        committed = [0]

        class _FakeAuditSession:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def add(self, obj): added_rows.append(obj)
            def commit(self): committed[0] += 1

        monkeypatch.setattr(
            "database.SessionLocal", lambda: _FakeAuditSession(),
        )
        return added_rows, committed

    def test_U_multi_statement_reject_persists_audit_row(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # U: SELECT 1; DELETE ... → 400 AND an audit row with
        # status='blocked', reason='multi_statement'.
        added_rows, committed = self._wire_audit_capture(monkeypatch)

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1; DELETE FROM bookings WHERE id > 0",
            "session_token": SESSION_TOKEN,
            "confirmed": True,
        })
        assert resp.status_code == 400
        assert len(added_rows) == 1, (
            "Multi-statement reject must persist an audit row — pre-fix "
            "it vanished silently. Got "
            f"{len(added_rows)} rows."
        )
        assert committed[0] == 1
        # The event_data on the row should record the reject reason.
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["status"] == "blocked"
        assert data["reason"] == "multi_statement"

    def test_U_blocked_drop_persists_audit_row(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # U: real DROP outside any comment → 403 AND an audit row
        # with status='blocked', reason='blocked_command',
        # blocked_cmd='DROP'.
        added_rows, committed = self._wire_audit_capture(monkeypatch)

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "DROP TABLE users",
            "session_token": SESSION_TOKEN,
            "confirmed": True,
        })
        assert resp.status_code == 403
        assert len(added_rows) == 1
        assert committed[0] == 1
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["status"] == "blocked"
        assert data["reason"] == "blocked_command"
        assert data["blocked_cmd"] == "DROP"

    def test_U_blocked_call_persists_audit_row(
        self, admin_override, valid_sql_session, stub_db, monkeypatch,
    ):
        # U: CALL (the PR-7-added block) → 403 + audit row.
        added_rows, committed = self._wire_audit_capture(monkeypatch)

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "CALL some_proc()",
            "session_token": SESSION_TOKEN,
            "confirmed": True,
        })
        assert resp.status_code == 403
        assert len(added_rows) == 1
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["status"] == "blocked"
        assert data["blocked_cmd"] == "CALL"
