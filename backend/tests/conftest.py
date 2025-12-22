"""
Pytest configuration and shared fixtures.

This module loads environment variables from .env and provides
fixtures for API integration tests.
"""
import os
import pytest
from pathlib import Path

# Load .env file before any imports that might use settings
from dotenv import load_dotenv

# Load .env from backend directory
backend_dir = Path(__file__).parent.parent
env_file = backend_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)

# Set test database before any imports
os.environ["DATABASE_URL"] = "sqlite:///./tag_test.db"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (may require API keys)"
    )


# Shared test database setup
TEST_DATABASE_URL = "sqlite:///./tag_test.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_app_dependency_override():
    """Set up database dependency override for all tests."""
    from database import Base, get_db
    from main import app

    # Override the dependency
    app.dependency_overrides[get_db] = override_get_db
    yield
    # Clean up after all tests
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def setup_test_database():
    """Create fresh test database for each test."""
    from database import Base
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Get a test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def has_dvla_api_key():
    """Check if DVLA API key is configured."""
    key = os.environ.get("DVLA_API_KEY_TEST", "")
    return bool(key and not key.startswith("your_"))


@pytest.fixture(scope="session")
def has_os_places_api_key():
    """Check if OS Places API key is configured."""
    key = os.environ.get("OS_PLACES_API_KEY", "")
    return bool(key and not key.startswith("your_"))


@pytest.fixture(scope="session")
def has_stripe_keys():
    """Check if Stripe keys are configured."""
    secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
    return bool(secret_key and secret_key.startswith(("sk_test_", "sk_live_")))


@pytest.fixture(autouse=True)
def skip_integration_without_keys(request, has_dvla_api_key, has_os_places_api_key, has_stripe_keys):
    """Automatically skip integration tests if API keys are missing."""
    if request.node.get_closest_marker("integration"):
        test_name = request.node.name.lower()

        # Check which API this test needs
        if "dvla" in test_name or "vehicle" in test_name:
            if not has_dvla_api_key:
                pytest.skip("DVLA API key not configured in .env")

        elif "address" in test_name or "postcode" in test_name:
            if not has_os_places_api_key:
                pytest.skip("OS Places API key not configured in .env")

        elif "stripe" in test_name or "payment" in test_name:
            if not has_stripe_keys:
                pytest.skip("Stripe keys not configured in .env")
