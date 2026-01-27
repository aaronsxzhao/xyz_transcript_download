# XYZ Podcast Transcript Tool - Docker Image
# Optimized for cloud deployment (Fly.io, Railway, etc.)

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Build frontend if not already built
RUN if [ -d "web/dist" ]; then echo "Frontend already built"; else echo "No frontend dist found"; fi

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
