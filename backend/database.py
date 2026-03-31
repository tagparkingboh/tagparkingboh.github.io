"""
Database configuration and session management.
Uses PostgreSQL via Railway.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Get database URL from environment (PostgreSQL required)
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

# Handle PostgreSQL URL format from some providers (postgres:// vs postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,          # Base number of connections to keep open
    max_overflow=20,       # Extra connections when pool is exhausted
    pool_timeout=30,       # Seconds to wait for a connection before timeout
    pool_recycle=1800,     # Recycle connections after 30 minutes
    pool_pre_ping=True,    # Test connections before using them
)

# Set timezone to UK for all database connections
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_timezone(dbapi_connection, connection_record):
    """Set PostgreSQL session timezone to UK (Europe/London)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET timezone TO 'Europe/London'")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from db_models import Base
    Base.metadata.create_all(bind=engine)
