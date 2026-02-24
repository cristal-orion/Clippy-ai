"""
Pydantic schemas for request/response validation
"""

from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime

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
    max_tokens: Optional[int] = Field(default=500, ge=10, le=4000)
    allowed_domains: Optional[List[str]] = None

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
    """Schema for a chat message"""
    role: str
    content: str

class WidgetChatRequest(BaseModel):
    """Schema for widget chat request (uses config_id)"""
    config_id: str
    messages: List[ChatMessage]

class ChatResponse(BaseModel):
    """Schema for chat response"""
    message: str
    animation: Optional[str] = None
