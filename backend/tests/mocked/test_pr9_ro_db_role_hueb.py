"""
HUEB tests for PR 9 of the 2026-05-29 security review: read-only DB role
+ separate connection pool for the admin SQL console.

PR 9 is defence in depth on top of PR 8:
  Layer 1 — require_admin + PIN session                    (existing)
  Layer 2 — SELECT/WITH prefix allow-list                  (PR 8)
  Layer 3 — comment-aware multi-statement + keyword gates  (PR 7)
  Layer 4 — SET TRANSACTION READ ONLY before user query    (PR 8 review)
  Layer 5 — tag_sql_console Postgres role (SELECT only)    (PR 9)

Layer 5 means even if every other layer somehow misfired, an
UPDATE/INSERT/DELETE would fail at the Postgres role level with
"permission denied for table ...".

Provisioning DDL was run inline on staging + prod 2026-05-30:
  CREATE ROLE tag_sql_console WITH LOGIN PASSWORD '...';
  GRANT CONNECT ON DATABASE railway TO tag_sql_console;
  GRANT USAGE ON SCHEMA public TO tag_sql_console;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO tag_sql_console;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ...;

The connection string for that role lives in Railway env as
SQL_CONSOLE_DATABASE_URL (distinct staging + prod passwords).

What this file pins:
  - execute_sql_query depends on get_sql_console_db, NOT get_db
  - get_sql_console_db yields None when SQL_CONSOLE_DATABASE_URL is
    unset → handler 503's (fail-closed)
  - audit_logs writes still flow through the RW SessionLocal — the
    RO role can't INSERT to audit_logs and that's intentional
"""
import sys
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi.testclient import TestClient

import main
from main import app, require_admin, execute_sql_query
from database import get_db, get_sql_console_db


SESSION_TOKEN = "test-session-token-pr9"


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


# ============================================================================
# Wiring pin: execute_sql_query uses get_sql_console_db, NOT get_db
# ============================================================================


class TestExecuteHandlerUsesReadOnlyDep:
    """Pin the dep wiring. A future commit that reverts the dep back
    to get_db re-introduces the RW write path — fail loudly here."""

    def test_H_handler_depends_on_get_sql_console_db(self):
        sig = inspect.signature(execute_sql_query)
        db_param = sig.parameters.get("db")
        assert db_param is not None, "execute_sql_query lost its db param"
        # The default value is a fastapi.Depends instance with a
        # `.dependency` attribute pointing at the resolver function.
        dep = getattr(db_param.default, "dependency", None)
        assert dep is get_sql_console_db, (
            f"execute_sql_query.db dep should be get_sql_console_db; "
            f"got {dep!r}. A revert to get_db re-opens the write path."
        )

    def test_U_handler_does_NOT_depend_on_get_db(self):
        sig = inspect.signature(execute_sql_query)
        db_param = sig.parameters.get("db")
        dep = getattr(db_param.default, "dependency", None)
        assert dep is not get_db, (
            "execute_sql_query.db dep is get_db — that's the read/write "
            "connection. PR 9 swapped it to get_sql_console_db."
        )


# ============================================================================
# Fail-closed: 503 when SQL_CONSOLE_DATABASE_URL is unset
# ============================================================================


class TestFailClosedWhenEnvUnset:
    """When the RO connection isn't configured (env var unset, or
    engine init failed), the handler returns 503 rather than silently
    falling back to a writable connection. Same shape as PR 6's
    SMS_WEBHOOK_SECRET fail-closed."""

    def test_U_env_unset_returns_503(self, admin_override, valid_sql_session):
        # U: get_sql_console_db yields None → handler 503's. Override
        # the dep to do exactly that so the test doesn't depend on a
        # real env var state.
        def _none_dep():
            yield None
        app.dependency_overrides[get_sql_console_db] = _none_dep
        try:
            client = TestClient(app)
            resp = client.post("/api/admin/sql/execute", json={
                "query": "SELECT 1",
                "session_token": SESSION_TOKEN,
            })
            assert resp.status_code == 503, (
                f"Expected 503 when SQL_CONSOLE_DATABASE_URL is unset; "
                f"got {resp.status_code}. A silent fallback to get_db "
                f"would re-open the write path."
            )
            assert "not configured" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_sql_console_db, None)


# ============================================================================
# Audit persistence still uses the RW SessionLocal
# ============================================================================


class TestAuditUsesReadWriteConnection:
    """The RO role can't INSERT to audit_logs (that's why we have a
    separate role at all). Pin that _persist_sql_audit still uses
    database.SessionLocal — the RW connection — so the audit trail
    keeps landing."""

    def test_H_audit_helper_uses_rw_session_local(self):
        # H: inspect execute_sql_query's source for the audit helper
        # call site. _persist_sql_audit is defined inline. The audit
        # session must come from `database.SessionLocal` (the RW
        # engine), NOT from `db` (the RO dep).
        src = inspect.getsource(execute_sql_query)
        # The PR 7 audit helper used `from database import SessionLocal`
        # inside _persist_sql_audit; PR 9 must NOT have replaced that
        # with `db` (the RO param) or SqlConsoleSessionLocal.
        assert "SessionLocal" in src, (
            "_persist_sql_audit lost its SessionLocal reference. "
            "Audit writes need the RW engine — the RO role can't "
            "INSERT to audit_logs."
        )
        assert "SqlConsoleSessionLocal" not in src, (
            "Audit helper tries to use SqlConsoleSessionLocal (the RO "
            "engine). RO can't INSERT — audit rows will silently fail. "
            "Use database.SessionLocal (RW) for audit."
        )


# ============================================================================
# get_sql_console_db dep behaviour
# ============================================================================


class TestGetSqlConsoleDbDep:
    """Unit tests for the dep itself."""

    def test_E_yields_none_when_session_local_unset(self, monkeypatch):
        # E: SqlConsoleSessionLocal is None (env var was unset at
        # import time) → dep yields None. The handler's 503 path
        # depends on this.
        import database as db_module
        monkeypatch.setattr(
            db_module, "SqlConsoleSessionLocal", None, raising=False,
        )
        # The dep is a generator; advance it once.
        gen = db_module.get_sql_console_db()
        value = next(gen)
        assert value is None

    def test_H_yields_session_when_session_local_set(self, monkeypatch):
        # H: SqlConsoleSessionLocal is bound to an engine → dep yields
        # a session and closes it on exit.
        import database as db_module
        fake_session = MagicMock()
        fake_session.close = MagicMock()

        class _FakeSessionLocal:
            def __call__(self):
                return fake_session

        monkeypatch.setattr(
            db_module, "SqlConsoleSessionLocal", _FakeSessionLocal(),
            raising=False,
        )
        gen = db_module.get_sql_console_db()
        value = next(gen)
        assert value is fake_session
        # Exhaust the generator to trigger the close.
        try:
            next(gen)
        except StopIteration:
            pass
        fake_session.close.assert_called_once()
