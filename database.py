"""
Database configuration and session management
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

# Database URL - Try persistent SQLite, fallback to in-memory if permissions fail
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/clippy_data.db")

print(f"🗄️  Database URL: {DATABASE_URL}")

# Create engine with error handling
try:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
    )
    # Test connection
    with engine.connect() as conn:
        print("✅ Database connection successful!")
except Exception as e:
    print(f"⚠️  Persistent database failed: {e}")
    print("🔄 Falling back to in-memory SQLite...")
    DATABASE_URL = "sqlite:///:memory:"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    print("✅ In-memory database initialized (data will reset on restart)")

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print("✅ Database initialized successfully!")
