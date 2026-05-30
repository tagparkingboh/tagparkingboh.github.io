"""
HUEB tests for PR 8 of the 2026-05-29 security review: hard SELECT-only
admin SQL console.

PR 8 enforces a one-line policy:

  > Admin SQL console is read-only. Production writes happen through
  > explicit scripts or code changes, not through the browser.

Implementation:
  - ALLOWED_SQL_PREFIXES = ('SELECT', 'WITH')
  - cleaned_upper.startswith(ALLOWED_SQL_PREFIXES) gates the request
  - rejection → 403 + audit row {status: blocked, reason: select_only,
    attempted_cmd: <first token>}
  - is_write_operation, WRITE_SQL_COMMANDS, and the
    requires_confirmation response shape are gone

NOT allowed in narrow PR 8 (intentional):
  - INSERT / UPDATE / DELETE   — the obvious writes
  - CALL                       — already in BLOCKED_SQL_COMMANDS from
                                 PR 7; PR 8 just makes the path 403
                                 a step earlier with reason=select_only
                                 instead of reason=blocked_command,
                                 either is correct
  - EXPLAIN                    — EXPLAIN ANALYZE on an INSERT/UPDATE
                                 actually executes the write; safely
                                 allowing EXPLAIN would mean parsing
                                 the inner statement (out of scope)
  - SHOW                       — not in scope; uncommon admin need
  - BEGIN / COMMIT / ROLLBACK  — transactional control isn't a read

NO env-var override per the 2026-05-30 scoping decision:
  > the failure mode is exactly the bad one: someone flips it during
  > stress and forgets

Deferred to PRs 9/10: read-only DB role + two-person approval.
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
    ALLOWED_SQL_PREFIXES,
    require_admin,
)
from database import get_db


SESSION_TOKEN = "test-session-token-pr8"


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
def valid_sql_session(admin_user):
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
def stub_db():
    # 2026-05-30 PR 9: execute_sql_query now uses get_sql_console_db
    # (the read-only role dep), not get_db. We override BOTH so the
    # mock reaches the handler and the 503 fail-closed path doesn't
    # trip in tests that aren't testing it.
    from database import get_sql_console_db
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()

    def _gen():
        yield db
    app.dependency_overrides[get_db] = _gen
    app.dependency_overrides[get_sql_console_db] = _gen
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_sql_console_db, None)


@pytest.fixture
def capture_audit(monkeypatch):
    """Capture AuditLog rows written via the dedicated audit
    SessionLocal so tests can introspect status/reason/attempted_cmd."""
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


# ============================================================================
# Sanity: the policy constant + dead code removal
# ============================================================================


class TestPolicyConstants:
    """The PR 8 contract is encoded in ALLOWED_SQL_PREFIXES. Pin it
    and pin the dead-code removals so a future refactor that
    re-introduces is_write_operation / WRITE_SQL_COMMANDS /
    requires_confirmation is loud."""

    def test_H_allowed_prefixes_is_select_and_with_only(self):
        assert ALLOWED_SQL_PREFIXES == ('SELECT', 'WITH'), (
            f"Expected ('SELECT', 'WITH'); got {ALLOWED_SQL_PREFIXES}. "
            f"Adding EXPLAIN or SHOW here without parsing the inner "
            f"statement is a write loophole — EXPLAIN ANALYZE INSERT "
            f"actually executes the INSERT."
        )

    def test_E_is_write_operation_removed(self):
        # E: pre-PR-8 helper for the dead write-confirmation flow.
        # The PR 8 gate uses cleaned_upper.startswith directly.
        assert not hasattr(main, "is_write_operation"), (
            "is_write_operation was removed by PR 8 (dead code after "
            "the SELECT-only switch). A new import means the write "
            "confirmation flow snuck back in."
        )

    def test_E_write_sql_commands_removed(self):
        # E: the list of write keywords no longer exists.
        assert not hasattr(main, "WRITE_SQL_COMMANDS"), (
            "WRITE_SQL_COMMANDS was removed by PR 8. If it's back "
            "someone re-introduced the write-confirmation logic."
        )


# ============================================================================
# H: SELECT and WITH succeed
# ============================================================================


class TestAllowedQueriesSucceed:
    """SELECT and WITH (CTE) reach the executor; everything else is
    rejected upstream."""

    def _stub_select_result(self, stub_db, rows=None, cols=None):
        rows = rows or [(1,)]
        cols = cols or ["x"]
        mock_result = MagicMock()
        mock_result.fetchmany.return_value = rows
        mock_result.keys.return_value = cols
        def _exec(stmt, *a, **kw):
            if "STATEMENT_TIMEOUT" in str(stmt).upper():
                return MagicMock()
            return mock_result
        stub_db.execute.side_effect = _exec

    def test_H_select_returns_200(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # H: SELECT → 200, data returned.
        self._stub_select_result(stub_db)
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_type"] == "SELECT"
        assert body["row_count"] == 1

    def test_H_with_cte_returns_200(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # H: WITH ... SELECT (CTE) → 200, query_type='WITH'.
        self._stub_select_result(stub_db)
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "WITH recent AS (SELECT id FROM bookings LIMIT 5) "
                     "SELECT * FROM recent",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_type"] == "WITH"

    def test_E_leading_block_comment_before_select_still_works(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # E: /* comment */ SELECT 1 — the cleaned_query normalisation
        # from PR 7 strips the comment so the prefix check sees SELECT.
        # Pre-PR-8 this also worked, but the path went through the
        # SELECT branch via a different check. Pin the post-PR-8
        # behavior so a refactor that drops cleaned_query usage
        # accidentally fails.
        self._stub_select_result(stub_db)
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "/* daily count */ SELECT count(*) FROM bookings",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200


# ============================================================================
# U: every non-SELECT/WITH command is 403'd with audit
# ============================================================================


class TestNonSelectIsRejected:
    """The core PR 8 contract: every write keyword (and every other
    non-SELECT/WITH prefix) returns 403 with reason='select_only' in
    the audit row. db.execute MUST NOT have been called on the user
    query."""

    def _assert_blocked(
        self, query, expected_attempted_cmd, added_rows, stub_db,
    ):
        # The user query must NOT have reached db.execute. Only the
        # statement_timeout SET would have been called; everything
        # else would mean the gate didn't fire first.
        user_query_calls = [
            c for c in stub_db.execute.call_args_list
            if expected_attempted_cmd in str(c.args[0]).upper()
        ]
        assert user_query_calls == [], (
            f"User query reached db.execute ({len(user_query_calls)} "
            f"calls). The PR 8 SELECT-only gate must fire BEFORE the "
            f"executor runs."
        )

        assert len(added_rows) == 1, (
            f"Expected one audit row for the rejected attempt; got "
            f"{len(added_rows)}. PR 8 must audit every reject — "
            f"forensic visibility is the only reason this is an "
            f"acceptable change."
        )
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["status"] == "blocked"
        assert data["reason"] == "select_only"
        assert data["attempted_cmd"] == expected_attempted_cmd

    def test_U_insert_403(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        added_rows, _ = capture_audit
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "INSERT INTO bookings (id) VALUES (1)",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        assert "read-only" in resp.json()["detail"].lower()
        self._assert_blocked("INSERT INTO bookings (id) VALUES (1)",
                              "INSERT", added_rows, stub_db)

    def test_U_update_403(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        added_rows, _ = capture_audit
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "UPDATE bookings SET status='cancelled' WHERE id=1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        self._assert_blocked(
            "UPDATE bookings SET status='cancelled' WHERE id=1",
            "UPDATE", added_rows, stub_db,
        )

    def test_U_delete_403(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        added_rows, _ = capture_audit
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "DELETE FROM bookings WHERE id=1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        self._assert_blocked("DELETE FROM bookings WHERE id=1",
                              "DELETE", added_rows, stub_db)

    def test_E_block_comment_before_update_still_403(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        # E: /* maintenance */ UPDATE — the comment-strip from PR 7
        # leaves UPDATE at the start of cleaned_upper. Pre-PR-7 this
        # was the bypass that triggered the review fix.
        added_rows, _ = capture_audit
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "/* maintenance */ UPDATE bookings SET status='x'",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        # attempted_cmd is computed from cleaned_upper.split()[0] →
        # UPDATE, not /*.
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["attempted_cmd"] == "UPDATE"

    def test_B_explain_select_403_intentional(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        # B: EXPLAIN ANALYZE INSERT/UPDATE actually executes the write
        # under Postgres, so allowing EXPLAIN safely would require
        # parsing the inner statement. PR 8 takes the narrow path:
        # EXPLAIN is rejected. If a future PR wants EXPLAIN it must
        # add the inner-statement parse + audit story.
        added_rows, _ = capture_audit
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "EXPLAIN SELECT * FROM bookings",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["attempted_cmd"] == "EXPLAIN"


# ============================================================================
# Regression: requires_confirmation response shape is gone
# ============================================================================


class TestNoMoreConfirmationFlow:
    """Pre-PR-8 an UPDATE without confirmed=True returned a 200 with
    {"requires_confirmation": true}. PR 8 removed that path — it now
    returns a 403 directly. Pin the shape so a future commit can't
    silently reintroduce the confirmation step."""

    def test_E_update_without_confirmed_returns_403_not_confirmation_prompt(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "UPDATE bookings SET status='x' WHERE id=1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 403, (
            f"PR 8 contract: UPDATE → 403 directly. Got "
            f"{resp.status_code}. If 200 with requires_confirmation — "
            f"the confirmation flow was reintroduced."
        )
        body = resp.json()
        assert "requires_confirmation" not in body
        assert "operation_type" not in body

    def test_E_confirmed_true_does_not_bypass_select_only_gate(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        # E: Even if a stale FE sends confirmed=True, the SELECT-only
        # gate still rejects. The field is accepted by the model
        # (back-compat) but ignored by the handler.
        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "DELETE FROM bookings WHERE id=1",
            "session_token": SESSION_TOKEN,
            "confirmed": True,  # Stale FE flag — must NOT bypass.
        })
        assert resp.status_code == 403


# ============================================================================
# 2026-05-30 review-fix HIGH: DB-enforced read-only transaction
# ============================================================================
#
# Reviewer flagged that the prefix allow-list isn't actually read-only.
# Both of these bypass the prefix check but mutate data:
#
#   WITH d AS (DELETE FROM bookings WHERE id=1 RETURNING id) SELECT * FROM d
#   SELECT * INTO temp_export FROM bookings LIMIT 10
#
# Fix: prefix check stays as UX pre-filter; the real boundary is
# SET TRANSACTION READ ONLY before the user query. Postgres refuses
# writes, SELECT...INTO, and CTE-nested writes when the txn is RO.


class TestReadOnlyTransactionEnforcement:
    """Pin the order of SET TRANSACTION READ ONLY relative to the user
    query, and pin that Postgres-raised "read only transaction" errors
    propagate as 400."""

    def _capture_execute_sequence(self, stub_db):
        """Stub db.execute to record every SQL statement issued, in
        order, and return a default fetchmany result on the user query.
        Useful for asserting order-of-operations."""
        sql_calls = []
        mock_result = MagicMock()
        mock_result.fetchmany.return_value = [(1,)]
        mock_result.keys.return_value = ["x"]

        def _exec(stmt, *a, **kw):
            sql_calls.append(str(stmt))
            return mock_result

        stub_db.execute.side_effect = _exec
        return sql_calls

    def test_H_set_transaction_read_only_runs_before_user_query(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # H: SET TRANSACTION READ ONLY must be issued BEFORE the user
        # query (Postgres requires it as the first statement of the
        # transaction, and the security guarantee is: RO mode active
        # when the query runs). Also pin that it runs before
        # statement_timeout SET, so a malicious query can't somehow
        # observe an un-RO window.
        sql_calls = self._capture_execute_sequence(stub_db)

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1 FROM bookings",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200

        ro_idx = next(
            (i for i, s in enumerate(sql_calls)
             if "SET TRANSACTION READ ONLY" in s.upper()),
            None,
        )
        timeout_idx = next(
            (i for i, s in enumerate(sql_calls)
             if "STATEMENT_TIMEOUT" in s.upper() and "30" in s),
            None,
        )
        user_query_idx = next(
            (i for i, s in enumerate(sql_calls)
             if "FROM BOOKINGS" in s.upper()),
            None,
        )

        assert ro_idx is not None, (
            "SET TRANSACTION READ ONLY was never executed. The prefix "
            "gate is not the security boundary; the RO transaction is."
        )
        assert ro_idx < timeout_idx, (
            f"SET TRANSACTION READ ONLY (idx {ro_idx}) must come "
            f"BEFORE SET statement_timeout (idx {timeout_idx}) — "
            f"Postgres requires RO be set first in the transaction."
        )
        assert ro_idx < user_query_idx, (
            "User query ran before SET TRANSACTION READ ONLY — there "
            "is an RO-less window. Security boundary breached."
        )

    def test_U_with_delete_returning_select_propagates_postgres_error_as_400(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        # U: The CTE-nested-DELETE bypass. The prefix gate allows it
        # (starts with WITH). Postgres' read-only mode raises
        # "cannot execute DELETE in a read-only transaction" — the
        # existing exception handler converts that to 400.
        #
        # We simulate Postgres' rejection by raising on the user-query
        # execute call. The order-of-operations test above proves
        # the RO setup runs first; this test proves the rejection
        # path lands the user a clean 400 + audit.
        added_rows, _ = capture_audit

        def _exec(stmt, *a, **kw):
            s_upper = str(stmt).upper()
            if "STATEMENT_TIMEOUT" in s_upper or "READ ONLY" in s_upper:
                return MagicMock()
            # User query — simulate Postgres rejecting the inner DELETE.
            raise Exception(
                "cannot execute DELETE in a read-only transaction"
            )

        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "WITH d AS (DELETE FROM bookings WHERE id=1 "
                     "RETURNING id) SELECT * FROM d",
            "session_token": SESSION_TOKEN,
        })

        assert resp.status_code == 400, (
            f"Postgres' RO-transaction rejection should propagate as "
            f"400 'Query error: ...'. Got {resp.status_code}."
        )
        assert "read-only transaction" in resp.json()["detail"].lower()
        # The error path also writes an audit row.
        assert len(added_rows) == 1
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["status"] == "error"

    def test_U_select_into_propagates_postgres_error_as_400(
        self, admin_override, valid_sql_session, stub_db, capture_audit,
    ):
        # U: SELECT * INTO temp_export FROM bookings — this creates a
        # new table (Postgres syntactic sugar for CREATE TABLE AS
        # SELECT). Read-only mode refuses it. Prefix gate let it
        # through (starts with SELECT); RO transaction is the
        # actual gate.
        added_rows, _ = capture_audit

        def _exec(stmt, *a, **kw):
            s_upper = str(stmt).upper()
            if "STATEMENT_TIMEOUT" in s_upper or "READ ONLY" in s_upper:
                return MagicMock()
            raise Exception(
                "cannot execute SELECT INTO in a read-only transaction"
            )

        stub_db.execute.side_effect = _exec

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT * INTO temp_export FROM bookings LIMIT 10",
            "session_token": SESSION_TOKEN,
        })

        assert resp.status_code == 400
        assert "read-only transaction" in resp.json()["detail"].lower()
        assert len(added_rows) == 1
        import json as _json
        data = _json.loads(added_rows[0].event_data)
        assert data["status"] == "error"

    def test_E_defensive_rollback_runs_before_set_transaction(
        self, admin_override, valid_sql_session, stub_db,
    ):
        # E: db.rollback() runs before SET TRANSACTION READ ONLY so
        # any lingering session state from get_db init can't prevent
        # the RO directive from taking effect (Postgres requires
        # SET TRANSACTION to be the first statement after BEGIN).
        sql_calls = []
        rollback_calls = []
        mock_result = MagicMock()
        mock_result.fetchmany.return_value = [(1,)]
        mock_result.keys.return_value = ["x"]

        def _exec(stmt, *a, **kw):
            sql_calls.append(("execute", str(stmt)))
            return mock_result

        def _rollback():
            rollback_calls.append(len(sql_calls))

        stub_db.execute.side_effect = _exec
        stub_db.rollback.side_effect = _rollback

        client = TestClient(app)
        resp = client.post("/api/admin/sql/execute", json={
            "query": "SELECT 1",
            "session_token": SESSION_TOKEN,
        })
        assert resp.status_code == 200
        assert rollback_calls, (
            "Defensive db.rollback() never ran. Without it, lingering "
            "session-init state could open a transaction before our "
            "SET TRANSACTION READ ONLY, which Postgres then ignores."
        )
        # The rollback fired BEFORE any SQL was executed.
        ro_after_rollback = any(
            "SET TRANSACTION READ ONLY" in stmt.upper()
            for op, stmt in sql_calls
            if sql_calls.index(("execute", stmt)) >= rollback_calls[0]
        )
        assert ro_after_rollback
