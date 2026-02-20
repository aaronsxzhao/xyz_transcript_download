# syntax=docker/dockerfile:1
# XYZ Podcast Transcript Tool - Cloud-Optimized Docker Image
# Uses BuildKit cache mounts for fast rebuilds

# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend-build
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY web/ .
RUN npm run build

# --- Stage 2: Python runtime ---
FROM python:3.11-slim

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    aria2 \
    curl \
    libstdc++6

# Node.js binary (for yt-dlp YouTube JS challenge solving)
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
RUN node --version

WORKDIR /app

# Install Python deps first (cached unless requirements change)
COPY requirements-cloud.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements-cloud.txt

# Copy application code (changes frequently, so last)
COPY . .

# Overwrite web/dist with freshly built frontend
COPY --from=frontend-build /web/dist /app/web/dist

RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV XYZ_DATA_DIR=/data
ENV WHISPER_MODE=api
ENV WHISPER_API_PROVIDER=groq

EXPOSE 8080
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8080}/api/health')" || exit 1

CMD python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --access-log --log-config /app/uvicorn_log_config.json
