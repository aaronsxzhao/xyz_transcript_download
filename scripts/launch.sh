#!/bin/bash
#
# XYZ Podcast Transcript Tool - Launcher Script
# This script sets up the environment and launches the web UI
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# App configuration
APP_NAME="XYZ Podcast"
APP_DIR="${HOME}/.xyz-podcast"
VENV_DIR="${APP_DIR}/venv"
DATA_DIR="${APP_DIR}/data"
REQUIREMENTS_HASH_FILE="${APP_DIR}/.requirements_hash"
DEFAULT_PORT=8000

# Get the directory where the app is located
if [[ "$0" == *".app/Contents/MacOS/"* ]]; then
    # Running from .app bundle
    SCRIPT_DIR="$(cd "$(dirname "$0")/../Resources/app" && pwd)"
else
    # Running from source
    SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
fi

# Function to show error dialog (macOS)
show_error() {
    if command -v osascript &> /dev/null; then
        osascript -e "display dialog \"$1\" with title \"${APP_NAME} Error\" buttons {\"OK\"} default button \"OK\" with icon stop"
    else
        echo -e "${RED}Error: $1${NC}"
    fi
}

# Function to show notification (macOS)
show_notification() {
    if command -v osascript &> /dev/null; then
        osascript -e "display notification \"$1\" with title \"${APP_NAME}\""
    fi
}

# Function to check Python version
check_python() {
    local python_cmd=""
    
    # Try python3 first, then python
    for cmd in python3 python; do
        if command -v "$cmd" &> /dev/null; then
            version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            
            if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 9 ]]; then
                python_cmd="$cmd"
                break
            fi
        fi
    done
    
    if [[ -z "$python_cmd" ]]; then
        show_error "Python 3.9 or higher is required.\n\nPlease install Python from:\nhttps://www.python.org/downloads/\n\nOr use Homebrew:\nbrew install python@3.11"
        exit 1
    fi
    
    echo "$python_cmd"
}

# Function to check FFmpeg
check_ffmpeg() {
    if ! command -v ffmpeg &> /dev/null; then
        echo -e "${YELLOW}Warning: FFmpeg is not installed.${NC}"
        echo -e "${YELLOW}FFmpeg is required for audio processing.${NC}"
        echo ""
        echo "Install FFmpeg using:"
        echo "  brew install ffmpeg"
        echo ""
        echo "Or download from: https://ffmpeg.org/download.html"
        echo ""
        
        if command -v osascript &> /dev/null; then
            osascript -e 'display dialog "FFmpeg is not installed.\n\nFFmpeg is required for audio processing.\n\nInstall with: brew install ffmpeg" with title "XYZ Podcast" buttons {"Continue Anyway", "Quit"} default button "Quit"' 2>/dev/null
            if [[ $? -ne 0 ]]; then
                exit 1
            fi
        fi
    fi
}

# Function to get requirements hash
get_requirements_hash() {
    if [[ -f "${SCRIPT_DIR}/requirements.txt" ]]; then
        md5 -q "${SCRIPT_DIR}/requirements.txt" 2>/dev/null || md5sum "${SCRIPT_DIR}/requirements.txt" | cut -d' ' -f1
    fi
}

# Function to setup virtual environment
setup_venv() {
    local python_cmd="$1"
    
    echo -e "${BLUE}Setting up virtual environment...${NC}"
    
    # Create app directory
    mkdir -p "${APP_DIR}"
    mkdir -p "${DATA_DIR}"
    
    # Create venv if it doesn't exist
    if [[ ! -d "${VENV_DIR}" ]]; then
        echo "Creating virtual environment..."
        "$python_cmd" -m venv "${VENV_DIR}"
    fi
    
    # Activate venv
    source "${VENV_DIR}/bin/activate"
    
    # Check if requirements need to be installed
    local current_hash=$(get_requirements_hash)
    local stored_hash=""
    
    if [[ -f "${REQUIREMENTS_HASH_FILE}" ]]; then
        stored_hash=$(cat "${REQUIREMENTS_HASH_FILE}")
    fi
    
    if [[ "${current_hash}" != "${stored_hash}" ]] || [[ -z "${stored_hash}" ]]; then
        echo -e "${BLUE}Installing dependencies (this may take a few minutes on first run)...${NC}"
        show_notification "Installing dependencies..."
        
        pip install --upgrade pip -q
        pip install -r "${SCRIPT_DIR}/requirements.txt" -q
        
        # Save hash
        echo "${current_hash}" > "${REQUIREMENTS_HASH_FILE}"
        echo -e "${GREEN}Dependencies installed successfully!${NC}"
    fi
}

# Function to find available port
find_available_port() {
    local port=$DEFAULT_PORT
    while lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; do
        port=$((port + 1))
        if [[ $port -gt 65535 ]]; then
            echo $DEFAULT_PORT
            return
        fi
    done
    echo $port
}

# Function to start the server
start_server() {
    local port=$(find_available_port)
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ${APP_NAME} - Web UI${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "  Server: ${BLUE}http://localhost:${port}${NC}"
    echo -e "  API Docs: ${BLUE}http://localhost:${port}/docs${NC}"
    echo ""
    echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop the server"
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo ""
    
    # Open browser after a short delay
    (sleep 2 && open "http://localhost:${port}") &
    
    # Set data directory
    export XYZ_DATA_DIR="${DATA_DIR}"
    
    # Start the server
    cd "${SCRIPT_DIR}"
    
    # Check if we have pre-built frontend
    if [[ -d "${SCRIPT_DIR}/web/dist" ]]; then
        # Use pre-built frontend - serve via FastAPI static files
        python -m uvicorn api.main:app --host 0.0.0.0 --port "${port}"
    else
        # Development mode - need npm
        echo -e "${YELLOW}Note: Running in development mode${NC}"
        python -m uvicorn api.main:app --host 0.0.0.0 --port "${port}" --reload
    fi
}

# Main execution
main() {
    echo ""
    echo -e "${BLUE}Starting ${APP_NAME}...${NC}"
    echo ""
    
    # Check Python
    python_cmd=$(check_python)
    echo -e "${GREEN}✓ Python found: ${python_cmd}${NC}"
    
    # Check FFmpeg
    check_ffmpeg
    
    # Setup environment
    setup_venv "$python_cmd"
    echo -e "${GREEN}✓ Environment ready${NC}"
    
    # Start server
    start_server
}

# Handle Ctrl+C gracefully
trap 'echo ""; echo -e "${YELLOW}Shutting down...${NC}"; exit 0' INT TERM

# Run main
main "$@"
