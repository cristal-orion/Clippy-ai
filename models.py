"""
Database models for Clippy AI Platform
"""

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class User(Base):
    """User account model"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    configs = relationship("ClippyConfig", back_populates="owner", cascade="all, delete-orphan")

class ClippyConfig(Base):
    """Clippy widget configuration model"""
    __tablename__ = "clippy_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(String(50), unique=True, index=True, nullable=False)  # Public ID for embedding
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="configs")

    # Clippy Configuration
    agent = Column(String(50), default="Clippy")
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    encrypted_api_key = Column(Text, nullable=False)  # Encrypted API key

    # AI Settings
    system_prompt = Column(Text, nullable=True)
    welcome_message = Column(Text, nullable=True)
    rag_content = Column(Text, nullable=True)
    temperature = Column(Float, default=0.8)
    max_tokens = Column(Integer, default=500)

    # Security
    allowed_domains = Column(Text, nullable=True)  # JSON array of allowed domains

    # Metadata
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_used = Column(DateTime(timezone=True), nullable=True)
