"""Launch the packaged FastAPI app for the desktop shell."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the desktop backend server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    return parser.parse_args()


def configure_desktop_environment() -> None:
    os.environ.setdefault("XYZ_DESKTOP_MODE", "1")

    # Packaged desktop builds default to local-only mode unless the caller
    # intentionally supplies cloud credentials.
    for key in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_JWT_SECRET"):
        os.environ.setdefault(key, "")


def main() -> None:
    configure_desktop_environment()
    args = parse_args()

    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
