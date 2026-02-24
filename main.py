"""
Clippy AI Backend - FastAPI + LiteLLM Proxy + Authentication
Universal AI provider router for Clippy widget with user management
Version 2.0 - Multi-user authentication system with SQLite database
"""

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
import os
import json
import uuid
from datetime import datetime, timedelta
import litellm
from litellm import acompletion
from cryptography.fernet import Fernet

# Import custom modules
from database import get_db, init_db
from models import User, ClippyConfig
from schemas import (
    UserCreate, UserLogin, UserResponse, Token,
    ClippyConfigCreate, ClippyConfigUpdate, ClippyConfigResponse, ClippyConfigWithEmbed,
    ChatMessage, WidgetChatRequest, ChatResponse
)
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_active_user
)

# Encryption key (in production, load from environment)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", Fernet.generate_key())
if isinstance(ENCRYPTION_KEY, str):
    ENCRYPTION_KEY = ENCRYPTION_KEY.encode()
cipher_suite = Fernet(ENCRYPTION_KEY)

# FastAPI app
app = FastAPI(
    title="Clippy AI Backend",
    description="Universal AI provider proxy for Clippy widget with user management",
    version="2.0.0"
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    print("=" * 80)
    print("🚀 CLIPPY AI BACKEND V2.0 WITH AUTHENTICATION STARTING...")
    print("=" * 80)
    init_db()
    print("✅ Database initialized!")
    print(f"📊 Database URL: {os.getenv('DATABASE_URL', 'not set')}")
    print(f"🔐 JWT Secret: {'SET' if os.getenv('JWT_SECRET_KEY') else 'NOT SET - AUTHENTICATION WILL FAIL!'}")
    print(f"🔑 Encryption Key: {'SET' if os.getenv('ENCRYPTION_KEY') else 'NOT SET'}")
    print("=" * 80)

# ============ CORS Configuration ============
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ Configuration ============
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "groq")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama-3.3-70b-versatile")
DEFAULT_API_KEY = os.getenv("DEFAULT_API_KEY", "")

# Rate limiting (simple in-memory, use Redis for production)
rate_limit_requests = {}
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

# ============ Helper Functions ============

def encrypt_api_key(api_key: str) -> str:
    """Encrypt API key for secure storage"""
    return cipher_suite.encrypt(api_key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key for use"""
    return cipher_suite.decrypt(encrypted_key.encode()).decode()

def format_model_name(provider: str, model: str) -> str:
    """Format model name for LiteLLM"""
    return f"{provider}/{model}"

def check_rate_limit(client_ip: str) -> bool:
    """Simple in-memory rate limiting"""
    now = datetime.now()
    minute_ago = now.timestamp() - 60

    if client_ip in rate_limit_requests:
        rate_limit_requests[client_ip] = [
            ts for ts in rate_limit_requests[client_ip] if ts > minute_ago
        ]
    else:
        rate_limit_requests[client_ip] = []

    if len(rate_limit_requests[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        return False

    rate_limit_requests[client_ip].append(now.timestamp())
    return True

def get_public_url() -> str:
    """Get public URL for embed code generation"""
    return os.getenv("PUBLIC_URL", "http://localhost:8000")

# ============ Static Files ============
import pathlib
static_dir = pathlib.Path(__file__).parent / "static"

# Serve clippy-embed.js with no-cache headers (always fresh for embedded sites)
@app.get("/static/clippy-embed.js")
async def serve_embed_js():
    embed_file = static_dir / "clippy-embed.js"
    if not embed_file.exists():
        raise HTTPException(status_code=404, detail="Embed script not found")
    return FileResponse(
        str(embed_file),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ============ Root Redirect ============
from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    """Redirect root to dashboard"""
    return RedirectResponse(url="/static/dashboard.html", status_code=302)

# ============ Authentication Endpoints ============

@app.post("/api/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Check if username already exists
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(new_user)
    )

@app.post("/api/auth/login", response_model=Token)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Login user and return JWT token"""
    # Find user by email
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.from_orm(user)
    )

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information"""
    return UserResponse.from_orm(current_user)

# ============ Clippy Configuration Endpoints ============

@app.post("/api/configs", response_model=ClippyConfigWithEmbed, status_code=status.HTTP_201_CREATED)
async def create_config(
    config_data: ClippyConfigCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new Clippy configuration"""
    # Generate unique config ID
    config_id = str(uuid.uuid4())[:8]

    # Encrypt API key
    encrypted_key = encrypt_api_key(config_data.api_key)

    # Convert allowed_domains to JSON string
    allowed_domains_json = json.dumps(config_data.allowed_domains) if config_data.allowed_domains else None

    # Create configuration
    new_config = ClippyConfig(
        config_id=config_id,
        name=config_data.name,
        description=config_data.description,
        agent=config_data.agent,
        provider=config_data.provider,
        model=config_data.model,
        encrypted_api_key=encrypted_key,
        system_prompt=config_data.system_prompt,
        welcome_message=config_data.welcome_message,
        rag_content=config_data.rag_content,
        temperature=config_data.temperature,
        max_tokens=config_data.max_tokens,
        allowed_domains=allowed_domains_json,
        user_id=current_user.id
    )

    db.add(new_config)
    db.commit()
    db.refresh(new_config)

    # Generate embed code
    public_url = get_public_url()
    embed_code = f'''<!-- Clippy AI Widget -->
<script src="{public_url}/static/clippy-embed.js" data-config-id="{config_id}"></script>'''

    response = ClippyConfigResponse.from_orm(new_config)
    return ClippyConfigWithEmbed(**response.dict(), embed_code=embed_code)

@app.get("/api/configs", response_model=List[ClippyConfigResponse])
async def list_configs(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all configurations for current user"""
    configs = db.query(ClippyConfig).filter(ClippyConfig.user_id == current_user.id).all()
    return [ClippyConfigResponse.from_orm(config) for config in configs]

@app.get("/api/configs/{config_id}", response_model=ClippyConfigWithEmbed)
async def get_config(
    config_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get a specific configuration"""
    config = db.query(ClippyConfig).filter(
        ClippyConfig.config_id == config_id,
        ClippyConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    # Generate embed code
    public_url = get_public_url()
    embed_code = f'''<!-- Clippy AI Widget -->
<script src="{public_url}/static/clippy-embed.js" data-config-id="{config_id}"></script>'''

    response = ClippyConfigResponse.from_orm(config)
    return ClippyConfigWithEmbed(**response.dict(), embed_code=embed_code)

@app.put("/api/configs/{config_id}", response_model=ClippyConfigResponse)
async def update_config(
    config_id: str,
    config_data: ClippyConfigUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a configuration"""
    config = db.query(ClippyConfig).filter(
        ClippyConfig.config_id == config_id,
        ClippyConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    # Update fields
    update_data = config_data.dict(exclude_unset=True)

    # Handle API key re-encryption
    if "api_key" in update_data and update_data["api_key"]:
        update_data["encrypted_api_key"] = encrypt_api_key(update_data["api_key"])
        del update_data["api_key"]

    # Handle allowed_domains JSON conversion
    if "allowed_domains" in update_data and update_data["allowed_domains"]:
        update_data["allowed_domains"] = json.dumps(update_data["allowed_domains"])

    for key, value in update_data.items():
        setattr(config, key, value)

    db.commit()
    db.refresh(config)

    return ClippyConfigResponse.from_orm(config)

@app.delete("/api/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    config_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a configuration"""
    config = db.query(ClippyConfig).filter(
        ClippyConfig.config_id == config_id,
        ClippyConfig.user_id == current_user.id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    db.delete(config)
    db.commit()

    return None

# ============ Widget Public Endpoints ============

@app.get("/api/widget/config/{config_id}")
async def widget_get_config(config_id: str, req: Request, db: Session = Depends(get_db)):
    """
    Public endpoint for widget to load its configuration.
    Returns only the fields needed by the widget (NO API key).
    """
    config = db.query(ClippyConfig).filter(ClippyConfig.config_id == config_id).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    # Domain whitelist check
    origin = req.headers.get("origin") or req.headers.get("referer") or ""
    if config.allowed_domains:
        allowed = json.loads(config.allowed_domains)
        if allowed:
            from urllib.parse import urlparse
            origin_host = urlparse(origin).hostname or ""
            if origin_host and not any(
                origin_host == d or origin_host.endswith("." + d) for d in allowed
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Domain not allowed"
                )

    return {
        "config": {
            "agent": config.agent,
            "provider": config.provider,
            "model": config.model,
            "system_prompt": config.system_prompt,
            "welcome_message": config.welcome_message,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
    }

@app.post("/api/test-connection")
async def test_connection(
    request: Request,
    current_user: User = Depends(get_current_active_user)
):
    """
    Test API key connection by making a minimal request to the provider.
    Requires authentication. API key is sent, tested, and never stored in the browser.
    """
    body = await request.json()
    provider = body.get("provider")
    model = body.get("model")
    api_key = body.get("api_key")

    if not provider or not model or not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="provider, model, and api_key are required"
        )

    try:
        model_name = format_model_name(provider, model)
        os.environ[f"{provider.upper()}_API_KEY"] = api_key

        response = await acompletion(
            model=model_name,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5
        )

        return {"status": "ok", "provider": provider, "model": model}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection failed: {str(e)}"
        )


@app.post("/api/widget/chat")
async def widget_chat(
    request: WidgetChatRequest,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Chat endpoint for embedded widgets
    Uses config_id to load configuration and API key (secure)
    NO AUTHENTICATION REQUIRED (public endpoint for widgets)
    """
    # Rate limiting
    client_ip = req.client.host
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again in a minute."
        )

    # Load configuration
    config = db.query(ClippyConfig).filter(ClippyConfig.config_id == request.config_id).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )

    # Update usage stats
    config.usage_count += 1
    config.last_used = datetime.utcnow()
    db.commit()

    # Decrypt API key
    api_key = decrypt_api_key(config.encrypted_api_key)

    # Build system prompt
    system_prompt = config.system_prompt or f"You are {config.agent}, helpful assistant."

    if config.rag_content:
        system_prompt += f"\n\nKNOWLEDGE BASE:\n{config.rag_content}\n\nUse this information to answer questions."

    # Add animation instructions
    system_prompt += """

CRITICAL FORMAT: Always end with "[ANIMATION: AnimationName]"
Choose animations based on context: Wave (greeting), Explain (help), Thinking (analyzing), Congratulate (success), Alert (warning).
"""

    # Prepare messages
    messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m.role, "content": m.content} for m in request.messages]
    ]

    try:
        # Call LiteLLM
        model_name = format_model_name(config.provider, config.model)

        # Set API key in environment
        os.environ[f"{config.provider.upper()}_API_KEY"] = api_key

        response = await acompletion(
            model=model_name,
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens
        )

        content = response.choices[0].message.content

        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": content
                }
            }],
            "usage": response.usage
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI Error: {str(e)}"
        )

# ============ URL Scraping + AI Refinement ============

@app.post("/api/scrape-url")
async def scrape_url(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Scrape a web URL and refine the extracted text using AI.
    Returns raw and refined text for use as RAG knowledge base.
    """
    import httpx
    from bs4 import BeautifulSoup

    body = await request.json()
    url = body.get("url", "").strip()
    provider = body.get("provider")
    model = body.get("model")
    api_key = body.get("api_key")
    config_id = body.get("config_id")

    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # Validate URL format
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # Resolve API key: use provided key, or decrypt from config_id
    if not api_key and config_id:
        config = db.query(ClippyConfig).filter(
            ClippyConfig.config_id == config_id,
            ClippyConfig.user_id == current_user.id
        ).first()
        if config:
            api_key = decrypt_api_key(config.encrypted_api_key)
            if not provider:
                provider = config.provider
            if not model:
                model = config.model

    if not api_key or not provider or not model:
        raise HTTPException(status_code=400, detail="provider, model, and api_key (or config_id) are required")

    # Step 1: Scrape the URL
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; ClippyBot/1.0)"
            })
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"HTTP error fetching URL: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching URL: {str(e)}")

    # Parse HTML and extract text
    soup = BeautifulSoup(html, "html.parser")

    # Extract page title
    title = soup.title.string.strip() if soup.title and soup.title.string else url

    # Remove unwanted elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Try to find main content area
    main_content = soup.find("main") or soup.find("article") or soup.find("body")
    if not main_content:
        raise HTTPException(status_code=400, detail="Could not extract content from the page")

    raw_text = main_content.get_text(separator="\n", strip=True)

    # Truncate to ~30000 chars
    if len(raw_text) > 30000:
        raw_text = raw_text[:30000] + "\n\n[... content truncated ...]"

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="No text content found on the page")

    # Step 2: AI Refinement
    try:
        model_name = format_model_name(provider, model)
        os.environ[f"{provider.upper()}_API_KEY"] = api_key

        refine_response = await acompletion(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sei un assistente che organizza contenuti web in knowledge base strutturate. "
                        "Prendi il testo grezzo estratto dal sito e riorganizzalo in formato Q&A o sezioni "
                        "tematiche chiare, rimuovendo contenuti irrilevanti (menu, cookie notices, footer). "
                        "Mantieni tutte le informazioni utili. Rispondi nella stessa lingua del contenuto originale."
                    )
                },
                {
                    "role": "user",
                    "content": f"Ecco il testo estratto dal sito {url}:\n\n{raw_text}"
                }
            ],
            temperature=0.3,
            max_tokens=4000
        )

        refined_text = refine_response.choices[0].message.content
    except Exception as e:
        # If AI refinement fails, return raw text with a warning
        return {
            "raw_text": raw_text,
            "refined_text": raw_text,
            "title": title,
            "url": url,
            "warning": f"AI refinement failed ({str(e)}), returning raw text"
        }

    return {
        "raw_text": raw_text,
        "refined_text": refined_text,
        "title": title,
        "url": url
    }

# ============ Legacy Endpoints (Backwards Compatibility) ============

@app.post("/api/config/save")
async def legacy_save_config(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Legacy endpoint for saving config from old platform UI
    Converts to new format
    """
    config_data = request.get("config", {})

    new_config_data = ClippyConfigCreate(
        name=request.get("name", "Untitled"),
        description=request.get("description"),
        agent=config_data.get("agent", "Clippy"),
        provider=config_data.get("provider", "groq"),
        model=config_data.get("model", "llama-3.3-70b-versatile"),
        api_key=config_data.get("api_key", ""),
        system_prompt=config_data.get("system_prompt"),
        rag_content=config_data.get("rag_content"),
        temperature=config_data.get("temperature", 0.8),
        max_tokens=config_data.get("max_tokens", 500),
        allowed_domains=None
    )

    return await create_config(new_config_data, current_user, db)

# ============ Health & Info Endpoints ============

@app.get("/")
async def root():
    """Serve the configuration UI"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        return {
            "status": "healthy",
            "service": "Clippy AI Backend",
            "version": "2.0.0",
            "features": ["authentication", "database", "multi-user"]
        }

@app.get("/dashboard.html")
async def dashboard():
    """Serve the dashboard UI"""
    dashboard_file = static_dir / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(str(dashboard_file))
    else:
        raise HTTPException(status_code=404, detail="Dashboard not found")

@app.get("/create")
async def create_page():
    """Serve the create/edit configuration page"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        raise HTTPException(status_code=404, detail="Create page not found")

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

# ============ Run Server ============
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")

    print(f"""
    🚀 Clippy AI Backend v2.0 Starting...

    📍 Server: http://{host}:{port}
    📖 Docs: http://{host}:{port}/docs
    🔧 Health: http://{host}:{port}/health

    ⚙️  Features:
       ✅ User Authentication (JWT)
       ✅ Database Persistence (SQLite)
       ✅ Multi-user Support
       ✅ Secure API Key Storage
       ✅ Configuration Management

    🔒 Security:
       - Rate Limit: {RATE_LIMIT_PER_MINUTE} req/min
       - CORS Origins: {ALLOWED_ORIGINS}
       - Encrypted API Keys: ✅
    """)

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
