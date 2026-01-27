# XYZ Podcast Transcript Tool - Docker Image
# Optimized for cloud deployment (Fly.io, Render, etc.)

FROM python:3.11-slim

# Install system dependencies including Node.js for frontend build
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Build frontend
WORKDIR /app/web
# Cache bust: 2026-01-27-v2
RUN ls -la src/lib/ && npm ci && npm run build
WORKDIR /app

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
CMD python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
