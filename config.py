"""
Configuration module for Xiaoyuzhou Podcast Tool.
Loads settings from environment variables with validation.
"""

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class ConfigError(Exception):
    """Configuration error."""
    pass


def _get_env(key: str, default: str = "") -> str:
    """Get environment variable with default."""
    return os.getenv(key, default)


def _get_env_int(key: str, default: int, min_val: Optional[int] = None) -> int:
    """Get environment variable as integer with validation."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        int_val = int(value)
        if min_val is not None and int_val < min_val:
            print(f"Warning: {key}={int_val} is less than minimum {min_val}, using {min_val}")
            return min_val
        return int_val
    except ValueError:
        print(f"Warning: {key}={value} is not a valid integer, using default {default}")
        return default


def _validate_choice(key: str, value: str, choices: List[str], default: str) -> str:
    """Validate that value is in allowed choices."""
    if value not in choices:
        print(f"Warning: {key}={value} is not valid. Must be one of {choices}. Using {default}")
        return default
    return value


# Base directory
BASE_DIR = Path(__file__).parent.absolute()

# Data directory
DATA_DIR = Path(_get_env("XYZ_DATA_DIR", str(BASE_DIR / "data")))

# Subdirectories
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
SUMMARIES_DIR = DATA_DIR / "summaries"
DATABASE_PATH = DATA_DIR / "xyz.db"
TOKENS_FILE = DATA_DIR / "tokens.json"
PID_FILE = DATA_DIR / "daemon.pid"
HEALTH_FILE = DATA_DIR / "daemon.health"

# Create directories if they don't exist
for directory in [DATA_DIR, AUDIO_DIR, TRANSCRIPTS_DIR, SUMMARIES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Logging configuration
LOG_LEVEL = _validate_choice(
    "LOG_LEVEL",
    _get_env("LOG_LEVEL", "INFO").upper(),
    ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    "INFO"
)

# LLM API Configuration (for summarization)
LLM_API_KEY = _get_env("LLM_API_KEY", "")
LLM_BASE_URL = _get_env("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = _get_env("LLM_MODEL", "gpt-4o")

# Validate LLM config
if not LLM_API_KEY:
    print("Warning: LLM_API_KEY not set. Summarization will not work.")

# Whisper Configuration
WHISPER_MODE = _validate_choice(
    "WHISPER_MODE",
    _get_env("WHISPER_MODE", "local"),
    ["local", "api"],
    "local"
)

VALID_WHISPER_MODELS = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "turbo"]
WHISPER_LOCAL_MODEL = _validate_choice(
    "WHISPER_LOCAL_MODEL",
    _get_env("WHISPER_LOCAL_MODEL", "small"),
    VALID_WHISPER_MODELS,
    "small"
)

# Backend: "auto" (detect best), "faster-whisper", "mlx-whisper"
# - auto: Uses mlx-whisper on Apple Silicon, faster-whisper elsewhere
# - faster-whisper: CTranslate2-based, works on CPU and NVIDIA GPU
# - mlx-whisper: MLX-based, optimized for Apple Silicon GPU (M1/M2/M3)
WHISPER_BACKEND = _validate_choice(
    "WHISPER_BACKEND",
    _get_env("WHISPER_BACKEND", "auto"),
    ["auto", "faster-whisper", "mlx-whisper"],
    "auto"
)

# Device: "auto" (detect), "cuda", "cpu"
WHISPER_DEVICE = _validate_choice(
    "WHISPER_DEVICE",
    _get_env("WHISPER_DEVICE", "auto"),
    ["auto", "cuda", "cpu"],
    "auto"
)

# Compute type: "auto" (detect), "float16", "int8", "int8_float16", "float32"
# - float16: Fast, requires GPU with FP16 support
# - int8: Faster, lower memory, works on CPU and GPU
# - int8_float16: INT8 weights with FP16 compute (GPU only)
# - float32: Slowest but most compatible
WHISPER_COMPUTE_TYPE = _validate_choice(
    "WHISPER_COMPUTE_TYPE",
    _get_env("WHISPER_COMPUTE_TYPE", "auto"),
    ["auto", "float16", "int8", "int8_float16", "float32"],
    "auto"
)

# Batch size for transcription (higher = faster but more memory)
# Recommended: 8-16 for GPU, 4-8 for CPU
WHISPER_BATCH_SIZE = _get_env_int("WHISPER_BATCH_SIZE", 0, min_val=0)  # 0 = auto

# API settings (only used if WHISPER_MODE=api)
# Provider: "openai", "groq" (Groq is free and very fast)
WHISPER_API_PROVIDER = _validate_choice(
    "WHISPER_API_PROVIDER",
    _get_env("WHISPER_API_PROVIDER", "groq"),
    ["openai", "groq"],
    "groq"
)

# OpenAI Whisper API settings
OPENAI_API_KEY = _get_env("OPENAI_API_KEY", "")
OPENAI_WHISPER_URL = "https://api.openai.com/v1"

# Groq Whisper API settings (free tier available, very fast)
GROQ_API_KEY = _get_env("GROQ_API_KEY", "")
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1"

# Determine which API to use
if WHISPER_API_PROVIDER == "groq":
    WHISPER_BASE_URL = GROQ_WHISPER_URL
    WHISPER_API_KEY = GROQ_API_KEY
    WHISPER_API_MODEL = "whisper-large-v3"  # Groq's model
else:
    WHISPER_BASE_URL = _get_env("WHISPER_BASE_URL", OPENAI_WHISPER_URL)
    WHISPER_API_KEY = OPENAI_API_KEY
    WHISPER_API_MODEL = "whisper-1"  # OpenAI's model

MAX_AUDIO_SIZE_MB = 25  # API limit

# Validate API config if using API mode
if WHISPER_MODE == "api":
    if WHISPER_API_PROVIDER == "groq" and not GROQ_API_KEY:
        print("Warning: WHISPER_MODE=api with groq provider but GROQ_API_KEY not set.")
        print("Get a free API key at: https://console.groq.com/keys")
    elif WHISPER_API_PROVIDER == "openai" and not OPENAI_API_KEY:
        print("Warning: WHISPER_MODE=api with openai provider but OPENAI_API_KEY not set.")

# Check interval for daemon (in seconds)
CHECK_INTERVAL = _get_env_int("XYZ_CHECK_INTERVAL", 3600, min_val=60)

# Token refresh interval (in seconds)
TOKEN_REFRESH_INTERVAL = _get_env_int("TOKEN_REFRESH_INTERVAL", 600, min_val=60)

# Request timeouts (in seconds)
REQUEST_TIMEOUT_CONNECT = _get_env_int("REQUEST_TIMEOUT_CONNECT", 30, min_val=5)
REQUEST_TIMEOUT_READ = _get_env_int("REQUEST_TIMEOUT_READ", 60, min_val=10)

# Retry configuration
MAX_RETRIES = _get_env_int("MAX_RETRIES", 3, min_val=1)
RETRY_BACKOFF = _get_env_int("RETRY_BACKOFF", 2, min_val=1)

# Disk space check (in MB) - warn if less than this available
MIN_DISK_SPACE_MB = _get_env_int("MIN_DISK_SPACE_MB", 500, min_val=100)

# Xiaoyuzhou API base URL
XYZ_API_BASE = "https://api.xiaoyuzhoufm.com"

# Request headers for Xiaoyuzhou API
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def validate_config() -> bool:
    """
    Validate the configuration and return True if valid.
    Prints warnings for any issues.
    """
    valid = True
    
    # Check data directory is writable
    try:
        test_file = DATA_DIR / ".write_test"
        test_file.touch()
        test_file.unlink()
    except (OSError, IOError) as e:
        print(f"Error: Cannot write to data directory {DATA_DIR}: {e}")
        valid = False
    
    # Check LLM API key
    if not LLM_API_KEY:
        print("Warning: LLM_API_KEY not configured")
    
    # Check Whisper config
    if WHISPER_MODE == "api" and not WHISPER_API_KEY:
        print(f"Error: WHISPER_MODE=api requires API key for {WHISPER_API_PROVIDER}")
        valid = False
    
    return valid


def get_config_summary() -> str:
    """Get a summary of current configuration."""
    return f"""
Configuration Summary:
  Data Directory: {DATA_DIR}
  Log Level: {LOG_LEVEL}
  Whisper Mode: {WHISPER_MODE}
  Whisper Model: {WHISPER_LOCAL_MODEL}
  LLM Model: {LLM_MODEL}
  Check Interval: {CHECK_INTERVAL}s
  Max Retries: {MAX_RETRIES}
"""
