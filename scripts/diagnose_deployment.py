"""Read deployment metadata and emit only a whitelist of diagnostic fields."""
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def safe_log_summary(text: str) -> dict:
    exceptions = [name for name in (
        "ModuleNotFoundError", "ImportError", "SyntaxError", "IndentationError",
        "TypeError", "NameError", "AttributeError", "RuntimeError", "ValueError",
        "OSError", "PermissionError", "FileNotFoundError", "MemoryError",
    ) if name + ":" in text]
    missing = re.findall(r"ModuleNotFoundError: No module named ['\"]([A-Za-z0-9_.]{1,100})['\"]", text)
    missing = [name for name in missing if not name.startswith(("eyJ", "sb_", "ghp_"))]
    frames = re.findall(r'File "(/app/[A-Za-z0-9_./-]+\.py)", line ([0-9]+)', text)
    return {
        "exception_types": exceptions,
        "missing_modules": sorted(set(missing)),
        "source_frames": [{"file": path, "line": int(line)} for path, line in frames[-10:]],
        "startup_complete": "Application startup complete" in text,
        "startup_failed": "Application startup failed" in text,
        "listen_ports": sorted(set(re.findall(r"Uvicorn running on http://[^/\s]+:([0-9]+)", text))),
        "out_of_memory": bool(re.search(r"out of memory|OOMKilled", text, re.I)),
        "tunnel_connected": "Registered tunnel connection" in text,
        "origin_unreachable": bool(re.search(r"Unable to reach the origin service|connection refused", text, re.I)),
        "tunnel_configuration_error": bool(re.search(r"failed to parse tunnel|error parsing tunnel token", text, re.I)),
    }


def safe_health(data: bytes) -> dict:
    try:
        value = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    result = {}
    if value.get("status") in ("ok", "healthy", "error", "unhealthy"):
        result["status"] = value["status"]
    revision = value.get("revision")
    if isinstance(revision, str) and (revision == "unknown" or re.fullmatch(r"[0-9a-f]{40}", revision)):
        result["revision"] = revision
    return result


def probe_public_api() -> None:
    url = "https://aipodcastsummary.online/api/health"
    result = {"probe": "python"}
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            result.update(http_status=response.status, health=safe_health(response.read(8192)))
    except urllib.error.HTTPError as exc:
        result["http_status"] = exc.code
        body = exc.read(16384).decode("utf-8", "replace")
        codes = re.findall(r"error\s+code\s*:?\s*([0-9]{3,4})", body, re.I)
        if codes:
            result["edge_error_codes"] = sorted(set(codes))
    except Exception as exc:
        result["error_type"] = type(exc).__name__
    print(json.dumps(result))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "health.json"
        probe = subprocess.run([
            "curl", "--silent", "--show-error", "--max-time", "15", "--output", str(path),
            "--write-out", "%{http_code}", url,
        ], capture_output=True, text=True, timeout=20)
        result = {"probe": "curl", "exit_code": probe.returncode}
        if probe.stdout.isdigit():
            result["http_status"] = int(probe.stdout)
        if path.exists():
            result["health"] = safe_health(path.read_bytes()[:8192])
        print(json.dumps(result))


def oci_json(arguments: list[str], query: str) -> dict:
    command = subprocess.run(["oci", *arguments, "--query", query, "--output", "json"],
                             capture_output=True, text=True, timeout=60)
    if command.returncode:
        error = re.search(r'"code"\s*:\s*"([A-Za-z0-9_.-]+)"', command.stderr)
        print(json.dumps({"oci_error": error.group(1) if error else "command_failed"}))
        return {}
    return json.loads(command.stdout)


def inspect_containers() -> None:
    instance = oci_json([
        "container-instances", "container-instance", "get", "--container-instance-id",
        os.environ["CONTAINER_INSTANCE_ID"],
    ], 'data.{state:"lifecycle-state",containers:containers[*].id}')
    print(json.dumps({"instance_state": instance.get("state"), "container_count": len(instance.get("containers") or [])}))
    for container_id in instance.get("containers") or []:
        container = oci_json([
            "container-instances", "container", "get", "--container-id", container_id,
        ], 'data.{name:"display-name",state:"lifecycle-state",image:"image-url",pull_policy:"image-pull-policy",exit_code:"current-runtime-state"."exit-code",restart_count:"restart-count",memory_gb:"resource-config"."memory-limit-in-gbs",port:"environment-variables".PORT}')
        if not re.fullmatch(r"[0-9]{1,5}", str(container.get("port"))):
            container["port"] = None
        image = container.get("image") or ""
        image = image.split("?", 1)[0]
        if "@" in image and "@sha256:" not in image:
            image = image.rsplit("@", 1)[-1]
        container["image"] = image
        print(json.dumps({"container": container}))
        for previous in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "container.log"
                arguments = ["oci", "container-instances", "container", "retrieve-logs",
                             "--container-id", container_id, "--file", str(path)]
                if previous:
                    arguments.extend(["--is-previous", "true"])
                command = subprocess.run(arguments, capture_output=True, timeout=60)
                result = {"container_name": container.get("name"), "previous_run": previous}
                if command.returncode == 0 and path.exists():
                    result["logs"] = safe_log_summary(path.read_text(errors="replace"))
                else:
                    result["logs_available"] = False
                print(json.dumps(result))


if __name__ == "__main__":
    probe_public_api()
    inspect_containers()
