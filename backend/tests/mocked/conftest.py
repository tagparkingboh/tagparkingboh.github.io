"""
Conftest for mocked tests - does NOT connect to database.

Tests in this directory are pure unit tests that don't need database access.
"""
import pytest


# Override the parent conftest fixtures to prevent database connection
@pytest.fixture(scope="session", autouse=True)
def setup_app_dependency_override():
    """No-op override - mocked tests don't need database."""
    yield


@pytest.fixture(autouse=True)
def setup_test_database():
    """No-op override - mocked tests don't need database."""
    yield
