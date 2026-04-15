"""
Database connection management for ScrumPilot.
Handles SQLAlchemy engine and session creation.
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is not set. "
        "Example: postgresql://user:password@localhost:5432/scrumpilot"
    )

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,
    max_overflow=10,
    echo=False,  # Set to True for SQL query logging during development
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


@contextmanager
def get_session() -> Session:
    """
    Context manager for database sessions.
    
    Usage:
        with get_session() as session:
            # do work
            session.commit()
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables():
    """
    Create all tables in the database.
    
    WARNING: This is for development/testing only.
    In production, use Alembic migrations instead.
    """
    from backend.db.models import Base
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully.")


if __name__ == "__main__":
    # Quick test of database connection
    try:
        with engine.connect() as conn:
            print(f"✅ Successfully connected to database: {DATABASE_URL.split('@')[1]}")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
