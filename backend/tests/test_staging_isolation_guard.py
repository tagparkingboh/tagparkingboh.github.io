"""Guard: a default test run must never open a connection to STAGING_DATABASE_URL.

The root tests/conftest.py only builds a staging engine when RUN_STAGING_DB_TESTS=1.
Without that opt-in, DATABASE_AVAILABLE is False and test_engine is None, so the
autouse `setup_test_database` (Base.metadata.create_all) — the one path that
actually connected to staging — is a no-op. This test pins that invariant so the
leak can't silently come back.
"""
import os

import pytest


def _root_conftest(request):
    pm = request.config.pluginmanager
    for plugin in pm.get_plugins():
        path = getattr(plugin, "__file__", "") or ""
        if path.replace("\\", "/").endswith("/tests/conftest.py"):
            return plugin
    return None


def test_no_staging_engine_without_optin(request):
    if os.environ.get("RUN_STAGING_DB_TESTS") == "1":
        pytest.skip("staging DB explicitly enabled via RUN_STAGING_DB_TESTS=1")

    conftest = _root_conftest(request)
    assert conftest is not None, "root tests/conftest.py plugin not found"

    # No engine, no sessionmaker, not 'available' -> the autouse
    # setup_test_database fixture hits `if not DATABASE_AVAILABLE or test_engine
    # is None: yield; return` and never runs create_all, so no connection to
    # staging can be opened during this run.
    assert conftest.DATABASE_AVAILABLE is False
    assert conftest.test_engine is None
    assert conftest.TestSessionLocal is None
