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

    # Interface / UI mode
    ui_mode = Column(String(20), default="classic")        # "classic" | "modern"
    accent_color = Column(String(20), default="#4f46e5")
    dark_mode = Column(Boolean, default=False)
    web_search_enabled = Column(Boolean, default=False)
    max_messages_per_conversation = Column(Integer, default=0)  # 0 = unlimited
    generative_ui = Column(Boolean, default=False)  # replies rendered as interactive UI (modern mode)

    # Privacy notice shown before the chat (GDPR) and lead delivery
    privacy_enabled = Column(Boolean, default=False)
    privacy_text = Column(Text, nullable=True)
    privacy_policy_url = Column(String(500), nullable=True)
    privacy_button_label = Column(String(80), nullable=True)
    lead_emails = Column(Text, nullable=True)  # comma-separated, up to 3
    lead_consent_text = Column(Text, nullable=True)
    data_retention_days = Column(Integer, default=90)  # leads and consent records are deleted after this

    # Security
    allowed_domains = Column(Text, nullable=True)  # JSON array of allowed domains

    # Metadata
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_used = Column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    """A contact left by a visitor through a bot's lead form"""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    config_id = Column(Integer, ForeignKey("clippy_configs.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    name = Column(String(120), nullable=False)
    email = Column(String(320), nullable=False)
    phone = Column(String(40), nullable=True)
    company = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)
    conversation = Column(Text, nullable=True)  # the visitor's own messages, for context
    page_url = Column(String(500), nullable=True)

    # What the visitor agreed to, kept with the lead (GDPR accountability)
    consent_text = Column(Text, nullable=False)
    privacy_consent_id = Column(String(36), nullable=True)

    delivery_status = Column(String(20), default="pending")  # pending | sent | failed | not_configured
    delivery_error = Column(String(300), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class ConsentEvent(Base):
    """A visitor accepting a bot's privacy notice. No IP or other identifier is stored."""
    __tablename__ = "consent_events"

    id = Column(String(36), primary_key=True)  # random UUID handed to the widget
    config_id = Column(Integer, ForeignKey("clippy_configs.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    text_version = Column(String(16), nullable=False)  # hash of the notice the visitor saw
    page_url = Column(String(500), nullable=True)
