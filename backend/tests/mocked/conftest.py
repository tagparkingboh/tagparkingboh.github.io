"""
Shared pytest fixtures and configuration for mocked tests.

This conftest.py ensures proper test isolation when running the full suite.
"""
import pytest
from sqlalchemy import event
from sqlalchemy import text
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from types import SimpleNamespace


def _sqlite_tables(Base):
    return [
        table for table in Base.metadata.sorted_tables
        if table.name != "users"
    ]


def _create_sqlite_users_table(engine):
    """Create the auth users table with SQLite-compatible list columns."""
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                phone VARCHAR(20),
                is_admin BOOLEAN NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                preferred_shift_types TEXT NOT NULL DEFAULT '[]',
                excluded_shift_types TEXT NOT NULL DEFAULT '[]',
                preferred_days_off TEXT NOT NULL DEFAULT '[]',
                auto_assign_excluded BOOLEAN NOT NULL DEFAULT 0,
                driver_type VARCHAR(20),
                preferred_start_time TIME,
                preferred_end_time TIME,
                is_fallback_driver BOOLEAN NOT NULL DEFAULT 0,
                window_overrun_minutes INTEGER NOT NULL DEFAULT 60,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME,
                last_login DATETIME
            )
        """))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_users_id ON users (id)"
        ))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
        ))


def _build_sqlite_sessionmaker():
    import db_models  # noqa: F401 - registers ORM tables on Base.metadata
    from database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _register_postgres_compat(dbapi_connection, _connection_record):
        dbapi_connection.create_function(
            "hashtext",
            1,
            lambda value: hash(value or "") & 0x7FFFFFFF,
        )
        dbapi_connection.create_function(
            "pg_advisory_xact_lock",
            1,
            lambda _value: None,
        )

    sqlite_tables = _sqlite_tables(Base)
    _create_sqlite_users_table(engine)
    Base.metadata.create_all(bind=engine, tables=sqlite_tables)
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        expire_on_commit=False,
    )
    return engine, sqlite_tables, TestingSessionLocal


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


@pytest.fixture(scope="session", autouse=True)
def setup_app_dependency_override():
    """Shadow parent conftest's staging-DB dependency override.

    Mocked tests must opt into their own fake/in-memory DB fixtures. The parent
    tests/conftest.py fixture points FastAPI at STAGING_DATABASE_URL/DATABASE_URL,
    which makes tests under tests/mocked dependent on real schema state.
    """
    yield


@pytest.fixture
def db_session():
    """Isolated SQLAlchemy session for mocked tests that need real ORM behavior.

    This is intentionally SQLite in-memory, not the configured Railway/staging
    database. Tests that request db_session also get FastAPI's get_db dependency
    pointed at the same session so endpoint calls and direct assertions see the
    same rows.
    """
    from database import Base, get_db
    from main import app

    engine, sqlite_tables, TestingSessionLocal = _build_sqlite_sessionmaker()
    db = TestingSessionLocal()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield db
    finally:
        db.close()
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=engine, tables=sqlite_tables)


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, request):
    """Keep the shell's ENVIRONMENT out of mocked tests.

    Mocked tests never send real email/SMS, so the env-gated staging guard
    (`ENVIRONMENT=staging`) must not leak in from the runner's shell or CI —
    it short-circuits send_email/send_sms to a suppressed "success" and breaks
    their no-key / exception / status-code assertions. Unset it before every
    test; a test that specifically exercises the staging guard sets
    ENVIRONMENT itself within its own body (which runs after this fixture).
    """
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    if request.node.get_closest_marker("integration"):
        pytest.skip("External integration tests are excluded from tests/mocked")

    state = {"engine": None, "tables": None, "SessionLocal": None}

    def get_sessionmaker():
        if state["SessionLocal"] is None:
            engine, tables, SessionLocal = _build_sqlite_sessionmaker()
            state.update({
                "engine": engine,
                "tables": tables,
                "SessionLocal": SessionLocal,
            })
        return state["SessionLocal"]

    def sessionlocal_proxy(*args, **kwargs):
        return get_sessionmaker()(*args, **kwargs)

    try:
        import database
        from database import Base, get_db
        from main import app

        monkeypatch.setattr(database, "engine", None, raising=False)
        monkeypatch.setattr(database, "SessionLocal", sessionlocal_proxy, raising=False)
        if request.module.__name__.endswith("test_pool_snapshot"):
            monkeypatch.setattr(
                database,
                "engine",
                SimpleNamespace(pool=SimpleNamespace(checkedin=lambda: 3)),
                raising=False,
            )

        def default_override_get_db():
            db = sessionlocal_proxy()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides.setdefault(get_db, default_override_get_db)
    except Exception:
        Base = None
        app = None
        get_db = None

    if hasattr(request.module, "TestSessionLocal"):
        monkeypatch.setattr(
            request.module,
            "TestSessionLocal",
            sessionlocal_proxy,
            raising=False,
        )

    yield

    if app is not None and get_db is not None:
        current = app.dependency_overrides.get(get_db)
        if getattr(current, "__name__", "") == "default_override_get_db":
            app.dependency_overrides.pop(get_db, None)
    if state["engine"] is not None and Base is not None:
        Base.metadata.drop_all(bind=state["engine"], tables=state["tables"])


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
