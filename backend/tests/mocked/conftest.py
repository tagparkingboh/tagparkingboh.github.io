"""
Shared pytest fixtures and configuration for mocked tests.

This conftest.py ensures proper test isolation when running the full suite.
"""
import pytest


@pytest.fixture(autouse=True)
def setup_test_database():
    """Override the parent conftest's same-named autouse fixture.

    Mocked tests use MagicMock + dependency_overrides; they never touch the
    real DB. The parent fixture (tests/conftest.py) calls
    Base.metadata.create_all on every test, which is a network round-trip
    per table to the staging/prod DB — adds several seconds per test when
    DATABASE_URL is set in .env. This no-op shadows it for tests/mocked/.
    """
    yield


@pytest.fixture(autouse=True)
def reset_app_state():
    """
    Automatically reset FastAPI app state after each test.

    This prevents test pollution when multiple test files use
    app.dependency_overrides.
    """
    yield

    # Clean up after each test
    try:
        from main import app
        app.dependency_overrides.clear()
    except ImportError:
        pass  # main not imported in this test


@pytest.fixture(scope="session", autouse=True)
def cleanup_at_end():
    """Final cleanup at the end of the test session."""
    yield

    try:
        from main import app
        app.dependency_overrides.clear()
    except ImportError:
        pass
