# XYZ Podcast Transcript Tool - Cloud-Optimized Docker Image
# Optimized for fast deployment on Render/Fly.io
# Uses pre-built frontend and cloud APIs (no torch/whisper)

FROM python:3.11-slim

# Install minimal system dependencies (no Node.js needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy cloud-optimized requirements (no torch/faster-whisper)
COPY requirements-cloud.txt .

# Install Python dependencies (fast - no 2GB torch download)
RUN pip install --no-cache-dir -r requirements-cloud.txt

# Copy application code
COPY . .

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
