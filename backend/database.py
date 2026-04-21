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

# Threshold tracking for event-driven snapshots
USAGE_THRESHOLDS = [50, 70, 85, 90]  # Percentages to trigger snapshots
_last_threshold_level = 0  # Track which threshold we're currently at/above


def _get_threshold_level(usage_percent: float) -> int:
    """Return the highest threshold that usage_percent meets or exceeds."""
    level = 0
    for threshold in USAGE_THRESHOLDS:
        if usage_percent >= threshold:
            level = threshold
    return level


def _record_threshold_snapshot(trigger: str, usage_percent: float, checked_out: int, overflow: int):
    """Record a pool snapshot when a threshold is crossed."""
    from db_models import DbPoolSnapshot, PoolHealthStatus
    from sqlalchemy.orm import Session

    try:
        # Determine health status
        if usage_percent >= 90:
            health = PoolHealthStatus.CRITICAL
        elif usage_percent >= 70:
            health = PoolHealthStatus.WARNING
        else:
            health = PoolHealthStatus.HEALTHY

        # Use a direct session (not from pool we're monitoring)
        db = SessionLocal()
        try:
            snapshot = DbPoolSnapshot(
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                checked_out=checked_out,
                overflow=overflow,
                checked_in=engine.pool.checkedin(),
                usage_percent=usage_percent,
                health_status=health,
                trigger=trigger,
            )
            db.add(snapshot)
            db.commit()
            logger.info(f"Pool snapshot recorded: {trigger} at {usage_percent}%")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Failed to record threshold snapshot: {e}")


# Get database URL from environment (PostgreSQL required)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Pool configuration - increased from 10+20 to handle traffic spikes
POOL_SIZE = 15
MAX_OVERFLOW = 30
POOL_WARNING_THRESHOLD = 0.7  # Warn when 70% of pool is in use

# Engine will be None if DATABASE_URL is not set (allows imports without DB)
engine = None

if DATABASE_URL:
    # Handle PostgreSQL URL format from some providers (postgres:// vs postgresql://)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=POOL_SIZE,       # Base number of connections to keep open
            max_overflow=MAX_OVERFLOW, # Extra connections when pool is exhausted
            pool_timeout=30,           # Seconds to wait for a connection before timeout
            pool_recycle=1800,         # Recycle connections after 30 minutes
            pool_pre_ping=True,        # Test connections before using them
        )
    except Exception as e:
        logger.warning(f"Failed to create database engine: {e}")
        engine = None


# Only register event listeners if engine was created successfully
if engine is not None:
    @event.listens_for(engine, "connect")
    def set_timezone(dbapi_connection, connection_record):
        """Set PostgreSQL session timezone to UK (Europe/London)."""
        cursor = dbapi_connection.cursor()
        cursor.execute("SET timezone TO 'Europe/London'")
        cursor.close()


    @event.listens_for(engine, "checkout")
    def check_pool_usage(dbapi_connection, connection_record, connection_proxy):
        """Log warning when connection pool usage is high and record threshold crossings."""
        global _last_threshold_level

        pool = engine.pool
        checked_out = pool.checkedout()
        overflow = max(0, pool.overflow())

        total_possible = POOL_SIZE + MAX_OVERFLOW
        current_usage = checked_out + overflow
        usage_percent = (current_usage / total_possible * 100) if total_possible > 0 else 0

        # Check if we've crossed up to a new threshold
        current_level = _get_threshold_level(usage_percent)
        if current_level > _last_threshold_level:
            _record_threshold_snapshot(f"crossed_{current_level}", usage_percent, checked_out, overflow)
            _last_threshold_level = current_level

        # Log warnings
        if usage_percent >= POOL_WARNING_THRESHOLD * 100:
            logger.warning(
                f"[DB POOL WARNING] High connection usage: {current_usage}/{total_possible} "
                f"({usage_percent:.0f}%) - checked_out={checked_out}, overflow={overflow}"
            )

        if usage_percent >= 90:
            logger.error(
                f"[DB POOL CRITICAL] Connection pool nearly exhausted: {current_usage}/{total_possible} "
                f"({usage_percent:.0f}%) - checked_out={checked_out}, overflow={overflow}"
            )


    @event.listens_for(engine, "checkin")
    def log_checkin(dbapi_connection, connection_record):
        """Log when connections are returned and record threshold drops."""
        global _last_threshold_level

        pool = engine.pool
        checked_out = pool.checkedout()
        overflow = max(0, pool.overflow())

        total_possible = POOL_SIZE + MAX_OVERFLOW
        current_usage = checked_out + overflow
        usage_percent = (current_usage / total_possible * 100) if total_possible > 0 else 0

        # Check if we've dropped below the current threshold level
        current_level = _get_threshold_level(usage_percent)
        if current_level < _last_threshold_level:
            # Record the drop - use the threshold we dropped below
            dropped_from = _last_threshold_level
            _record_threshold_snapshot(f"dropped_below_{dropped_from}", usage_percent, checked_out, overflow)
            _last_threshold_level = current_level

        logger.debug(
            f"[DB POOL] Connection returned - checked_out={checked_out}, overflow={overflow}"
        )


    @event.listens_for(engine, "invalidate")
    def log_invalidate(dbapi_connection, connection_record, exception):
        """Log when a connection is invalidated."""
        logger.warning(f"[DB POOL] Connection invalidated: {exception}")


    @event.listens_for(engine, "soft_invalidate")
    def log_soft_invalidate(dbapi_connection, connection_record):
        """Log when a connection is soft invalidated (will be recycled)."""
        logger.info("[DB POOL] Connection marked for recycle")


# SessionLocal will work with None engine for imports, but fail at runtime if used
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
