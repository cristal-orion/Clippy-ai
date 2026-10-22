# Clippy AI Backend v2.0 - Docker Image with Authentication & Database

# Interactive UI (OpenUI): builds static/clippy-ui.js and openui_prompt.txt
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui/build.mjs ./
COPY ui/src ./src
RUN npm run build

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY *.py ./
COPY static/ ./static/
COPY --from=ui /ui/out/clippy-ui.js ./static/clippy-ui.js
COPY --from=ui /ui/out/openui_prompt.txt /ui/out/openui_prompt_leads.txt ./

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run the application
CMD ["python", "main.py"]
