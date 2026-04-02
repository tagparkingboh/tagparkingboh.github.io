"""
Database configuration and session management.
Uses PostgreSQL via Railway.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
import os
import logging

logger = logging.getLogger(__name__)

# Get database URL from environment (PostgreSQL required)
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

# Handle PostgreSQL URL format from some providers (postgres:// vs postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Pool configuration
POOL_SIZE = 10
MAX_OVERFLOW = 20
POOL_WARNING_THRESHOLD = 0.7  # Warn when 70% of pool is in use

engine = create_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,       # Base number of connections to keep open
    max_overflow=MAX_OVERFLOW, # Extra connections when pool is exhausted
    pool_timeout=30,           # Seconds to wait for a connection before timeout
    pool_recycle=1800,         # Recycle connections after 30 minutes
    pool_pre_ping=True,        # Test connections before using them
)


@event.listens_for(engine, "connect")
def set_timezone(dbapi_connection, connection_record):
    """Set PostgreSQL session timezone to UK (Europe/London)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET timezone TO 'Europe/London'")
    cursor.close()


@event.listens_for(engine, "checkout")
def check_pool_usage(dbapi_connection, connection_record, connection_proxy):
    """Log warning when connection pool usage is high."""
    pool = engine.pool
    pool_size = pool.size()
    checked_out = pool.checkedout()
    overflow = pool.overflow()

    total_possible = POOL_SIZE + MAX_OVERFLOW
    current_usage = checked_out + overflow
    usage_percent = current_usage / total_possible if total_possible > 0 else 0

    if usage_percent >= POOL_WARNING_THRESHOLD:
        logger.warning(
            f"[DB POOL WARNING] High connection usage: {current_usage}/{total_possible} "
            f"({usage_percent:.0%}) - checked_out={checked_out}, overflow={overflow}"
        )

    if usage_percent >= 0.9:
        logger.error(
            f"[DB POOL CRITICAL] Connection pool nearly exhausted: {current_usage}/{total_possible} "
            f"({usage_percent:.0%}) - checked_out={checked_out}, overflow={overflow}"
        )


@event.listens_for(engine, "checkin")
def log_checkin(dbapi_connection, connection_record):
    """Log when connections are returned to pool (debug level)."""
    pool = engine.pool
    logger.debug(
        f"[DB POOL] Connection returned - checked_out={pool.checkedout()}, overflow={pool.overflow()}"
    )


@event.listens_for(engine, "invalidate")
def log_invalidate(dbapi_connection, connection_record, exception):
    """Log when a connection is invalidated."""
    logger.warning(f"[DB POOL] Connection invalidated: {exception}")


@event.listens_for(engine, "soft_invalidate")
def log_soft_invalidate(dbapi_connection, connection_record):
    """Log when a connection is soft invalidated (will be recycled)."""
    logger.info("[DB POOL] Connection marked for recycle")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pool_status():
    """Get current connection pool status for monitoring."""
    pool = engine.pool
    checked_out = pool.checkedout()
    # overflow() can be negative when pool hasn't grown beyond base size - clamp to 0
    overflow = max(0, pool.overflow())
    checked_in = pool.checkedin()
    total_connections = checked_out + overflow
    max_connections = POOL_SIZE + MAX_OVERFLOW
    # Ensure usage percent is never negative
    usage_percent = max(0, round(total_connections / max_connections * 100, 1))

    return {
        "pool_size": POOL_SIZE,
        "max_overflow": MAX_OVERFLOW,
        "checked_out": checked_out,
        "overflow": overflow,
        "checked_in": checked_in,
        "total_connections": total_connections,
        "max_connections": max_connections,
        "usage_percent": usage_percent,
    }


def init_db():
    """Initialize database tables."""
    from db_models import Base
    Base.metadata.create_all(bind=engine)
