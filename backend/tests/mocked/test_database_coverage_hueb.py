"""
Mocked coverage tests for database.py import-time pool wiring.

These load database.py under a temporary module name so fake engines and
patched SQLAlchemy event decorators do not leak into the app's real
`database` module used by the broader mocked suite.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


DATABASE_PATH = Path(__file__).resolve().parents[2] / "database.py"


def _load_database_under_test(env=None, create_engine_side_effect=None, listens_for_side_effect=None):
    env = dict(env or {})
    managed_keys = {"DATABASE_URL", "SQL_CONSOLE_DATABASE_URL"}
    previous = {key: os.environ.get(key) for key in managed_keys}
    for key in managed_keys:
        if key in env:
            os.environ[key] = env[key]
        else:
            os.environ.pop(key, None)

    module_name = f"_database_under_test_{id(env)}"
    spec = importlib.util.spec_from_file_location(module_name, DATABASE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    create_engine_mock = MagicMock(side_effect=create_engine_side_effect)
    listens_for_mock = MagicMock(side_effect=listens_for_side_effect)
    try:
        with patch("sqlalchemy.create_engine", create_engine_mock), \
             patch("sqlalchemy.event.listens_for", listens_for_mock):
            spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    return module, create_engine_mock, listens_for_mock


def _fake_engine(*, checkedout=0, overflow=0, checkedin=15):
    pool = SimpleNamespace(
        checkedout=MagicMock(return_value=checkedout),
        overflow=MagicMock(return_value=overflow),
        checkedin=MagicMock(return_value=checkedin),
    )
    return SimpleNamespace(pool=pool)


def _capturing_listeners():
    listeners = {}

    def _listens_for(target, event_name):
        def _decorator(func):
            listeners[event_name] = func
            return func

        return _decorator

    return listeners, _listens_for


class TestDatabaseImportCoverage:
    def test_postgres_database_url_is_normalized_and_pool_events_are_registered(self):
        listeners, listens_for = _capturing_listeners()
        engine = _fake_engine(checkedout=40, overflow=5, checkedin=0)

        module, create_engine, _ = _load_database_under_test(
            env={"DATABASE_URL": "postgres://user:pass@example.com/tag"},
            create_engine_side_effect=[engine],
            listens_for_side_effect=listens_for,
        )

        assert module.DATABASE_URL.startswith("postgresql://")
        create_engine.assert_called_once()
        assert create_engine.call_args.args[0].startswith("postgresql://")
        assert {"connect", "checkout", "checkin", "invalidate", "soft_invalidate"} <= set(listeners)

        cursor = MagicMock()
        connection = MagicMock()
        connection.cursor.return_value = cursor
        listeners["connect"](connection, MagicMock())
        cursor.execute.assert_called_once_with("SET timezone TO 'Europe/London'")
        cursor.close.assert_called_once()

        module._record_threshold_snapshot = MagicMock()
        module._last_threshold_level = 0
        listeners["checkout"](MagicMock(), MagicMock(), MagicMock())
        module._record_threshold_snapshot.assert_called_once_with("crossed_90", 100.0, 40, 5)
        assert module._last_threshold_level == 90

        module._record_threshold_snapshot.reset_mock()
        engine.pool.checkedout.return_value = 10
        engine.pool.overflow.return_value = -3
        listeners["checkin"](MagicMock(), MagicMock())
        module._record_threshold_snapshot.assert_called_once_with("dropped_below_90", 22.22222222222222, 10, 0)
        assert module._last_threshold_level == 0

        listeners["invalidate"](MagicMock(), MagicMock(), RuntimeError("lost connection"))
        listeners["soft_invalidate"](MagicMock(), MagicMock())

    def test_database_engine_creation_failure_leaves_engine_none(self):
        module, create_engine, _ = _load_database_under_test(
            env={"DATABASE_URL": "postgresql://bad-url"},
            create_engine_side_effect=RuntimeError("engine boom"),
        )

        create_engine.assert_called_once()
        assert module.engine is None

    def test_sql_console_url_is_normalized_and_session_dependency_closes(self):
        sql_engine = _fake_engine()
        module, create_engine, _ = _load_database_under_test(
            env={"SQL_CONSOLE_DATABASE_URL": "postgres://reader:pass@example.com/tag"},
            create_engine_side_effect=[sql_engine],
        )

        assert module.SQL_CONSOLE_DATABASE_URL.startswith("postgresql://")
        create_engine.assert_called_once()
        assert create_engine.call_args.args[0].startswith("postgresql://")
        assert module.sql_console_engine is sql_engine
        assert module.SqlConsoleSessionLocal is not None

        fake_session = MagicMock()
        module.SqlConsoleSessionLocal = MagicMock(return_value=fake_session)
        dep = module.get_sql_console_db()
        assert next(dep) is fake_session
        try:
            next(dep)
        except StopIteration:
            pass
        fake_session.close.assert_called_once()

    def test_sql_console_engine_failure_fails_closed(self):
        module, create_engine, _ = _load_database_under_test(
            env={"SQL_CONSOLE_DATABASE_URL": "postgresql://reader:pass@example.com/tag"},
            create_engine_side_effect=RuntimeError("sql console engine boom"),
        )

        create_engine.assert_called_once()
        assert module.sql_console_engine is None
        assert module.SqlConsoleSessionLocal is None

    def test_sql_console_dependency_none_branch_exhausts_cleanly(self):
        module, _, _ = _load_database_under_test()

        dep = module.get_sql_console_db()
        assert next(dep) is None
        try:
            next(dep)
        except StopIteration:
            pass
