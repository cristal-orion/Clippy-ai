# Clippy AI Platform

A self-hosted platform to create and embed AI-powered assistants on any website, styled as the classic Microsoft Office assistants (Clippy, Merlin, Rover, etc.).

Each assistant connects to your choice of AI provider (Groq, OpenAI, Anthropic, Ollama, and more) via [LiteLLM](https://github.com/BerriAI/litellm), with a full dashboard to manage configurations, knowledge bases (RAG), and embeddable widgets.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Docker](https://img.shields.io/badge/Docker-ready-blue)

## Features

- **Multiple AI Providers** — Groq, OpenAI, Anthropic, Google, Ollama (local), and 15+ more via LiteLLM
- **Classic Agents** — Clippy, Merlin, Rover, Bonzi, Genie, Links, and more
- **Knowledge Base (RAG)** — Upload files, paste text, or fetch and auto-process any URL with AI refinement
- **Embeddable Widget** — One `<script>` tag to add the assistant to any website
- **User Authentication** — JWT-based multi-user system with encrypted API key storage
- **Windows 95/98 UI** — Faithful retro design with gradient title bars and classic styling
- **Domain Whitelisting** — Restrict which domains can use your widget
- **Docker Ready** — One command to deploy

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- pip

### 1. Clone the repository

```bash
git clone https://github.com/cristal-orion/Clippy-ai.git
cd Clippy-ai
```

### 2. Create and configure the environment file

```bash
cp .env.example .env
```

Edit `.env` and generate real secret keys:

```bash
# Generate ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate JWT_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the generated values into your `.env` file.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the server

```bash
python main.py
```

The platform will be available at **http://localhost:8000**

- **Dashboard** — http://localhost:8000 (register an account, then create configurations)
- **API Docs** — http://localhost:8000/docs (Swagger UI)
- **Health Check** — http://localhost:8000/health

## Deploy with Docker

### Prerequisites

- Docker and Docker Compose

### 1. Clone and configure

```bash
git clone https://github.com/cristal-orion/Clippy-ai.git
cd Clippy-ai
cp .env.example .env
```

Edit `.env` with your generated keys (see Quick Start step 2).

### 2. Build and start

```bash
docker compose up --build -d
```

The platform will be available at **http://your-server-ip:8000**

### 3. Manage

```bash
# View logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code changes
docker compose down && docker compose up --build -d
```

## Production Deployment

For production, make sure to:

1. **Set strong keys** in `.env` (`JWT_SECRET_KEY`, `ENCRYPTION_KEY`)
2. **Set `PUBLIC_URL`** to your public domain (e.g. `https://clippy.yourdomain.com`)
3. **Set `ALLOWED_ORIGINS`** to your website domains instead of `*`
4. **Use a reverse proxy** (Nginx, Caddy, Traefik) with HTTPS in front of the container
5. **Keep the database volume** (`clippy-data`) — it persists user accounts and configurations across rebuilds

### Example: Nginx reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name clippy.yourdomain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Example: systemd service (without Docker)

```ini
[Unit]
Description=Clippy AI Backend
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/clippy
Environment="PATH=/opt/clippy/venv/bin"
ExecStart=/opt/clippy/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable clippy-backend
sudo systemctl start clippy-backend
```

## How to Use

### 1. Register and Login

Go to the dashboard and create an account.

### 2. Create a Configuration

- Choose an agent (Clippy, Merlin, Rover, etc.)
- Select an AI provider and model
- Enter your API key (stored encrypted on the server, never exposed to the browser)
- Customize the system prompt and welcome message
- Optionally add a knowledge base: paste text, upload a `.txt`/`.md` file, or fetch from a URL
- Save the configuration

### 3. Embed on Your Website

Copy the embed code from the dashboard and paste it into your website's HTML:

```html
<script src="https://your-clippy-server.com/static/clippy-embed.js" data-config-id="YOUR_CONFIG_ID"></script>
```

The assistant will appear in the bottom-right corner of your site. That's it.

## Project Structure

```
.
├── main.py              # FastAPI app and API endpoints
├── auth.py              # JWT authentication
├── database.py          # SQLAlchemy database setup
├── models.py            # Database models (User, ClippyConfig)
├── schemas.py           # Pydantic request/response schemas
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container image
├── docker-compose.yml   # Docker Compose config
├── .env.example         # Environment template
└── static/
    ├── index.html       # Configuration editor UI
    ├── dashboard.html   # User dashboard
    ├── clippy-embed.js  # Embeddable widget script
    ├── clippy.js        # ClippyJS animation engine
    └── assets/          # Agent sprites, sounds, CSS
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/register` | No | Register a new user |
| POST | `/api/auth/login` | No | Login and get JWT token |
| GET | `/api/auth/me` | Yes | Get current user info |
| POST | `/api/configs` | Yes | Create a new configuration |
| GET | `/api/configs` | Yes | List user configurations |
| GET | `/api/configs/{id}` | Yes | Get a specific configuration |
| PUT | `/api/configs/{id}` | Yes | Update a configuration |
| DELETE | `/api/configs/{id}` | Yes | Delete a configuration |
| POST | `/api/scrape-url` | Yes | Scrape a URL and refine with AI for RAG |
| POST | `/api/test-connection` | Yes | Test AI provider connection |
| GET | `/api/widget/config/{id}` | No | Public widget config (no API key exposed) |
| POST | `/api/widget/chat` | No | Public chat endpoint for embedded widgets |
| GET | `/health` | No | Health check |

## Supported AI Providers

Via LiteLLM, the platform supports:

| Provider | API Key Required |
|----------|-----------------|
| Groq | Yes |
| OpenAI | Yes |
| Anthropic | Yes |
| Google (Gemini) | Yes |
| Ollama (local) | No |
| DeepSeek | Yes |
| Together AI | Yes |
| Perplexity | Yes |
| xAI (Grok) | Yes |
| Azure OpenAI | Yes |
| AWS Bedrock | Yes |
| Cohere | Yes |
| Replicate | Yes |
| HuggingFace | Yes |

## License

MIT
