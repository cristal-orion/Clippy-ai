"""
Pydantic schemas for request/response validation
"""

import re

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Union, Dict, Any
from datetime import datetime

MAX_LEAD_EMAILS = 3
_EMAIL_RE = re.compile(r"^[^\s@,;:<>\"']+@[^\s@,;:<>\"']+\.[^\s@,;:<>\"']{2,}$")


def normalise_lead_emails(value: Optional[str]) -> Optional[str]:
    """'a@x.it; b@y.it' -> 'a@x.it, b@y.it'. Up to 3 valid, distinct addresses."""
    if value is None:
        return None
    emails = []
    for part in re.split(r"[,;\s]+", value.strip()):
        if not part:
            continue
        if not _EMAIL_RE.match(part) or len(part) > 320:
            raise ValueError(f"indirizzo email non valido: {part}")
        if part.lower() not in (e.lower() for e in emails):
            emails.append(part)
    if len(emails) > MAX_LEAD_EMAILS:
        raise ValueError(f"al massimo {MAX_LEAD_EMAILS} indirizzi email")
    return ", ".join(emails) or None


def normalise_http_url(value: Optional[str]) -> Optional[str]:
    """An absolute http(s) URL, or None when empty."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not re.match(r"^https?://[^\s/$.?#][^\s]*$", value, re.I) or len(value) > 500:
        raise ValueError("deve essere un indirizzo completo che inizia con https://")
    return value

# ============ User Schemas ============

class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

    @validator('username')
    def username_alphanumeric(cls, v):
        assert v.replace('_', '').replace('-', '').isalnum(), 'Username must be alphanumeric (with _ or -)'
        return v

class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    """Schema for user response (no password)"""
    id: int
    email: str
    username: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# ============ Clippy Config Schemas ============

class ClippyConfigBase(BaseModel):
    """Base schema for Clippy configuration"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    agent: str = "Clippy"
    provider: str
    model: str
    api_key: str  # Will be encrypted
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    rag_content: Optional[str] = None
    temperature: Optional[float] = Field(default=0.8, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=1200, ge=10, le=4000)
    allowed_domains: Optional[List[str]] = None
    ui_mode: str = "classic"
    accent_color: Optional[str] = "#4f46e5"
    dark_mode: Optional[bool] = False
    web_search_enabled: Optional[bool] = False
    max_messages_per_conversation: Optional[int] = Field(default=0, ge=0, le=1000)
    generative_ui: Optional[bool] = False
    privacy_enabled: Optional[bool] = False
    privacy_text: Optional[str] = Field(default=None, max_length=3000)
    privacy_policy_url: Optional[str] = None
    privacy_button_label: Optional[str] = Field(default=None, max_length=80)
    lead_emails: Optional[str] = None
    lead_consent_text: Optional[str] = Field(default=None, max_length=1000)
    data_retention_days: Optional[int] = Field(default=90, ge=7, le=730)

    _lead_emails = validator("lead_emails", allow_reuse=True)(normalise_lead_emails)
    _policy_url = validator("privacy_policy_url", allow_reuse=True)(normalise_http_url)

class ClippyConfigCreate(ClippyConfigBase):
    """Schema for creating a Clippy configuration"""
    pass

class ClippyConfigUpdate(BaseModel):
    """Schema for updating a Clippy configuration (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    agent: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None  # If provided, will be re-encrypted
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    rag_content: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=10, le=4000)
    allowed_domains: Optional[List[str]] = None
    ui_mode: Optional[str] = None
    accent_color: Optional[str] = None
    dark_mode: Optional[bool] = None
    web_search_enabled: Optional[bool] = None
    max_messages_per_conversation: Optional[int] = Field(None, ge=0, le=1000)
    generative_ui: Optional[bool] = None
    privacy_enabled: Optional[bool] = None
    privacy_text: Optional[str] = Field(None, max_length=3000)
    privacy_policy_url: Optional[str] = None
    privacy_button_label: Optional[str] = Field(None, max_length=80)
    lead_emails: Optional[str] = None
    lead_consent_text: Optional[str] = Field(None, max_length=1000)
    data_retention_days: Optional[int] = Field(None, ge=7, le=730)

    _lead_emails = validator("lead_emails", allow_reuse=True)(normalise_lead_emails)
    _policy_url = validator("privacy_policy_url", allow_reuse=True)(normalise_http_url)

class ClippyConfigResponse(BaseModel):
    """Schema for Clippy configuration response (no API key)"""
    id: int
    config_id: str  # Public embed ID
    name: str
    description: Optional[str]
    agent: str
    provider: str
    model: str
    system_prompt: Optional[str]
    welcome_message: Optional[str]
    rag_content: Optional[str]
    temperature: float
    max_tokens: int
    allowed_domains: Optional[str]  # JSON string
    ui_mode: str
    accent_color: Optional[str]
    dark_mode: Optional[bool]
    web_search_enabled: Optional[bool]
    max_messages_per_conversation: Optional[int]
    generative_ui: Optional[bool]
    privacy_enabled: Optional[bool]
    privacy_text: Optional[str]
    privacy_policy_url: Optional[str]
    privacy_button_label: Optional[str]
    lead_emails: Optional[str]
    lead_consent_text: Optional[str]
    data_retention_days: Optional[int]
    usage_count: int
    created_at: datetime
    updated_at: Optional[datetime]
    last_used: Optional[datetime]
    user_id: int

    class Config:
        from_attributes = True

class ClippyConfigWithEmbed(ClippyConfigResponse):
    """Schema for config response with embed code"""
    embed_code: str

# ============ Chat Schemas ============

class ChatMessage(BaseModel):
    """Schema for a chat message.

    `content` is either a plain string (text-only turn) or a list of content
    blocks (multimodal turn with attached images/PDFs), following the OpenAI /
    LiteLLM content-array format, e.g.:
        [{"type": "text", "text": "..."},
         {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
         {"type": "file", "file": {"filename": "doc.pdf", "file_data": "data:application/pdf;base64,..."}}]
    """
    role: str
    content: Union[str, List[Dict[str, Any]]]

class WidgetChatRequest(BaseModel):
    """Schema for widget chat request (uses config_id)"""
    config_id: str
    messages: List[ChatMessage]
    consent_id: Optional[str] = None  # required when the bot asks for privacy consent

class ChatResponse(BaseModel):
    """Schema for chat response"""
    message: str
    animation: Optional[str] = None
