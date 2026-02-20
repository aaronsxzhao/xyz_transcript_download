# XYZ Podcast Transcript Tool - Cloud-Optimized Docker Image
# Builds frontend in Docker so deployments always have fresh code

# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ .
RUN npm run build

# --- Stage 2: Python runtime ---
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    aria2 \
    curl \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js binary (for yt-dlp YouTube JS challenge solving)
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
RUN node --version

WORKDIR /app

COPY requirements-cloud.txt .
RUN pip install --no-cache-dir -r requirements-cloud.txt

COPY . .

# Overwrite web/dist with freshly built frontend
COPY --from=frontend-build /web/dist /app/web/dist

# Create data directory
RUN mkdir -p /data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV XYZ_DATA_DIR=/data
ENV WHISPER_MODE=api
ENV WHISPER_API_PROVIDER=groq

# Expose port (Render uses PORT env var, Fly.io uses 8080)
EXPOSE 8080
EXPOSE 10000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/api/health')" || exit 1

# Run the server (uses PORT env var if set, defaults to 8080)
# Use custom access log format that excludes query strings (to avoid logging tokens)
CMD python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --access-log --log-config /app/uvicorn_log_config.json
