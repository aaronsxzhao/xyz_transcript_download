"""Prepare the staged backend runtime used by Electron packaging."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


DESKTOP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = DESKTOP_DIR.parent
STAGE_DIR = DESKTOP_DIR / ".stage"
BACKEND_STAGE_DIR = STAGE_DIR / "backend"
BACKEND_APP_DIR = BACKEND_STAGE_DIR / "app"
BACKEND_RUNTIME_DIR = BACKEND_STAGE_DIR / "runtime"
TOOLS_STAGE_DIR = STAGE_DIR / "tools"


def reset_stage_dirs() -> None:
    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)

    BACKEND_APP_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    TOOLS_STAGE_DIR.mkdir(parents=True, exist_ok=True)


def copy_if_exists(src: Path, dest: Path) -> None:
    if not src.exists():
        return

    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def stage_backend_app() -> None:
    web_dist_dir = PROJECT_DIR / "web" / "dist"
    if not web_dist_dir.exists():
        raise RuntimeError("Frontend build not found at web/dist. Run the web build before packaging the desktop app.")

    for file_path in PROJECT_DIR.glob("*.py"):
        copy_if_exists(file_path, BACKEND_APP_DIR / file_path.name)

    for file_name in ("requirements.txt", "requirements-cloud.txt", ".env.example", "uvicorn_log_config.json"):
        copy_if_exists(PROJECT_DIR / file_name, BACKEND_APP_DIR / file_name)

    copy_if_exists(PROJECT_DIR / "api", BACKEND_APP_DIR / "api")
    copy_if_exists(PROJECT_DIR / "desktop" / "backend", BACKEND_APP_DIR / "desktop" / "backend")
    copy_if_exists(web_dist_dir, BACKEND_APP_DIR / "web" / "dist")


def get_runtime_python() -> Path:
    if sys.platform == "win32":
        return BACKEND_RUNTIME_DIR / "Scripts" / "python.exe"
    return BACKEND_RUNTIME_DIR / "bin" / "python3"


def build_virtualenv() -> None:
    subprocess.run([sys.executable, "-m", "venv", str(BACKEND_RUNTIME_DIR)], check=True, cwd=str(PROJECT_DIR))
    python_bin = get_runtime_python()
    subprocess.run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip"], check=True, cwd=str(PROJECT_DIR))
    subprocess.run(
        [str(python_bin), "-m", "pip", "install", "-r", str(PROJECT_DIR / "requirements.txt")],
        check=True,
        cwd=str(PROJECT_DIR),
    )


def stage_optional_tools() -> None:
    for tool_name in ("ffmpeg", "ffprobe"):
        resolved = shutil.which(tool_name)
        if not resolved and sys.platform == "win32":
            resolved = shutil.which(f"{tool_name}.exe")
        if resolved:
            copy_if_exists(Path(resolved), TOOLS_STAGE_DIR / Path(resolved).name)
        else:
            print(f"Warning: {tool_name} was not found on PATH. Some local media features may require it at runtime.")


def main() -> None:
    print("Preparing staged desktop backend...")
    reset_stage_dirs()
    stage_backend_app()
    build_virtualenv()
    stage_optional_tools()
    print(f"Desktop backend staged under: {BACKEND_STAGE_DIR}")


if __name__ == "__main__":
    main()
