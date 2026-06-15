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

def ensure_columns():
    """Add any missing columns to existing tables (lightweight SQLite migration)."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "clippy_configs" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("clippy_configs")}
    additions = {
        "ui_mode": "VARCHAR(20) DEFAULT 'classic'",
        "accent_color": "VARCHAR(20) DEFAULT '#4f46e5'",
        "dark_mode": "BOOLEAN DEFAULT 0",
        "web_search_enabled": "BOOLEAN DEFAULT 0",
        "max_messages_per_conversation": "INTEGER DEFAULT 0",
    }
    with engine.begin() as conn:
        for col, ddl in additions.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE clippy_configs ADD COLUMN {col} {ddl}"))
                print(f"🔧 Migration: added column clippy_configs.{col}")

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    print("✅ Database initialized successfully!")
