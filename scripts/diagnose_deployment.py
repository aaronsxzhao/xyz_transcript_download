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
        "auth_jwks_failures": text.count("[Auth] Failed to fetch JWKS"),
        "auth_api_failures": text.count("[Auth] Supabase API failed"),
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


def probe_access_controls() -> None:
    for path, expected in (
        ("/api/podcasts", 401), ("/api/settings", 401),
        ("/data/screenshots/__deployment_probe__.jpg", 403), ("/data/jobs.json", 404),
    ):
        result = subprocess.run([
            "curl", "--silent", "--show-error", "--location", "--max-time", "15",
            "--output", os.devnull, "--write-out", "%{http_code}",
            "https://aipodcastsummary.online" + path,
        ], capture_output=True, text=True, timeout=20)
        status = int(result.stdout) if result.stdout.isdigit() else 0
        print(json.dumps({"access_probe": path, "http_status": status,
                          "expected_status": expected, "passed": status == expected}))


def probe_loading() -> None:
    """Measure public page/assets without credentials or publishing page contents."""
    with tempfile.TemporaryDirectory() as directory:
        paths = ["/", "/api/auth/config"]
        for index, path in enumerate(paths):
            body = Path(directory) / f"body-{index}"
            headers = Path(directory) / f"headers-{index}"
            result = subprocess.run([
                "curl", "--silent", "--show-error", "--compressed", "--max-time", "20",
                "--output", str(body), "--dump-header", str(headers),
                "--write-out", '%{json}', "https://aipodcastsummary.online" + path,
            ], capture_output=True, text=True, timeout=25)
            try:
                metrics = json.loads(result.stdout)
            except ValueError:
                metrics = {}
            report = {key: metrics.get(key) for key in (
                "http_code", "time_connect", "time_starttransfer", "time_total", "size_download",
            )}
            if headers.exists():
                for line in headers.read_text().splitlines():
                    key, _, value = line.partition(":")
                    if key.lower() in {"cache-control", "content-encoding", "cf-cache-status"}:
                        report[key.lower()] = value.strip()[:100]
            print(json.dumps({"loading_probe": path, **report}))
            if path == "/" and body.exists():
                assets = re.findall(r'(?:src|href)="(/assets/[A-Za-z0-9_.-]+\.(?:js|css))"', body.read_text())
                paths.extend(list(dict.fromkeys(assets))[:8])


def inspect_containers() -> None:
    instance = oci_json([
        "container-instances", "container-instance", "get", "--container-instance-id",
        os.environ["CONTAINER_INSTANCE_ID"],
    ], 'data.{state:"lifecycle-state",containers:containers[*]."container-id"}')
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
        settings = oci_json([
            "container-instances", "container", "get", "--container-id", container_id,
        ], 'data."environment-variables"') or {}
        print(json.dumps({"provider_configuration": {
            name: bool(settings.get(name)) for name in (
                "GROQ_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "SUPABASE_JWT_SECRET",
            )
        }}))
        if settings.get("GROQ_API_KEY"):
            probe_groq_summary(settings["GROQ_API_KEY"])
        profile_library(settings)
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


def profile_library(settings: dict) -> None:
    bindings = {key: value for key, value in settings.items() if key.startswith("SUPABASE_") or key in {
        "GROQ_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "USE_SUPABASE",
    }}
    with tempfile.TemporaryDirectory() as directory:
        environment = {**os.environ, **bindings, "XYZ_DATA_DIR": directory,
                       "DISCORD_WEBHOOK_URL": "", "WHISPER_MODE": "api", "PYTHONPATH": "."}
        result = subprocess.run(["python", "scripts/profile_library.py"], env=environment,
                                capture_output=True, text=True, timeout=240)
        # Child output is still whitelisted so future logging cannot leak data.
        valid = False
        failed = result.returncode != 0
        for line in result.stdout.splitlines():
            try:
                report = json.loads(line)
            except ValueError:
                continue
            label = report.get("library_profile")
            if label not in {"stats", "podcasts", "recent_summaries", "channels", "queue", "settings",
                             "podcast_detail", "episodes", "summary", "transcript", "video_detail", "video_note", "empty", "failed",
                             "live_auth", "live_podcasts", "live_channels", "live_episodes", "live_summary", "live_transcript", "live_unavailable"}:
                continue
            safe = {"library_profile": label}
            safe.update({key: report[key] for key in ("milliseconds", "first_byte_ms", "wire_bytes", "database_requests", "response_bytes", "gzip_bytes", "status")
                         if isinstance(report.get(key), int) and 0 <= report[key] <= 10**9})
            print(json.dumps(safe))
            valid = True
            failed = failed or label == "failed" or ("status" in safe and safe["status"] != 200)
        if not valid or failed:
            raise RuntimeError("Read-only library profile did not pass")


def probe_groq_summary(api_key: str) -> None:
    """Verify the existing key with synthetic content; never log response bodies."""
    payload = {"model": "openai/gpt-oss-120b", "messages": [
        {"role": "user", "content": 'Reply with JSON: {"ok":true}'}
    ], "response_format": {"type": "json_object"}, "max_completion_tokens": 1024, "reasoning_effort": "low"}
    request = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions",
                                     data=json.dumps(payload).encode(), headers={
                                         "Authorization": "Bearer " + api_key,
                                         "Content-Type": "application/json", "User-Agent": "podcast-provider-check/1.0",
                                     })
    report = {"summary_provider_probe": "groq", "model": payload["model"]}
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
            content = data["choices"][0]["message"]["content"]
            report.update(http_status=response.status, valid_json=isinstance(json.loads(content), dict))
    except urllib.error.HTTPError as error:
        report.update(http_status=error.code, valid_json=False)
    except Exception as error:
        report.update(error_type=type(error).__name__, valid_json=False)
    print(json.dumps(report))


if __name__ == "__main__":
    probe_public_api()
    probe_access_controls()
    probe_loading()
    inspect_containers()
