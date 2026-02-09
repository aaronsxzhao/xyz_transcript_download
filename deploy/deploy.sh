#!/bin/bash
# =============================================================================
# Deploy/Update Script for Podcast Tool
# Run from the project root directory
# Usage: bash deploy/deploy.sh
# =============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "============================================"
echo "  Podcast Tool - Deploy / Update"
echo "============================================"
echo "  Project: $PROJECT_DIR"
echo ""

# --- Check for .env file ---
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Copy the template: cp deploy/.env.production .env"
    echo "Then edit it:      nano .env"
    exit 1
fi

# --- Pull latest code (if git repo) ---
if [ -d ".git" ]; then
    echo "[1/4] Pulling latest code..."
    git pull || echo "  Warning: git pull failed, continuing with current code"
else
    echo "[1/4] Not a git repo, skipping pull"
fi

# --- Build Docker image ---
echo ""
echo "[2/4] Building Docker image..."
docker build -t podcast-tool .

# --- Stop existing container (if any) ---
echo ""
echo "[3/4] Stopping existing container..."
docker stop podcast-tool 2>/dev/null && docker rm podcast-tool 2>/dev/null || true

# --- Start new container ---
echo ""
echo "[4/4] Starting new container..."
docker run -d \
    --name podcast-tool \
    --restart unless-stopped \
    --env-file .env \
    -e PORT=8080 \
    -e WHISPER_MODE=api \
    -e WHISPER_API_PROVIDER=groq \
    -e XYZ_DATA_DIR=/data \
    -p 8080:8080 \
    -v podcast_data:/data \
    podcast-tool

echo ""
echo "============================================"
echo "  Deployment Complete!"
echo "============================================"

# --- Health check ---
echo ""
echo "Waiting for app to start..."
sleep 5

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/health 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
    echo "  Health check: PASSED"
else
    echo "  Health check: PENDING (code: $HEALTH)"
    echo "  The app may still be starting up. Check logs with:"
    echo "    docker logs -f podcast-tool"
fi

echo ""
echo "Useful commands:"
echo "  View logs:     docker logs -f podcast-tool"
echo "  Restart:       docker restart podcast-tool"
echo "  Stop:          docker stop podcast-tool"
echo "  Check status:  docker ps"
echo ""
