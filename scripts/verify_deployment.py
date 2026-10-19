"""Wait until the public API serves the expected healthy application revision."""
import json
import os
import subprocess
import time


def verify_deployment(expected_revision: str, attempts: int = 18, interval: int = 10) -> bool:
    url = f"https://aipodcastsummary.online/api/health?revision={expected_revision}"
    for attempt in range(1, attempts + 1):
        try:
            # Cloudflare's browser integrity check rejects Python urllib on
            # this domain. Curl reaches the same public endpoint with TLS
            # verification enabled; keep the exact revision requirement.
            response = subprocess.run([
                "curl", "--fail", "--silent", "--show-error", "--max-time", "10",
                "--header", "Cache-Control: no-cache", "--write-out", "\n%{http_code}", url,
            ], capture_output=True, text=True, timeout=15)
            body, _, http_status = response.stdout.rpartition("\n")
            if response.returncode or http_status != "200":
                status = http_status if len(http_status) == 3 and http_status.isdigit() else "unknown"
                print(f"Attempt {attempt}: HTTP {status}, curl exit {response.returncode}", flush=True)
                if attempt < attempts:
                    time.sleep(interval)
                continue
            health = json.loads(body)
            if health.get("status") == "ok" and health.get("revision") == expected_revision:
                print(f"Deployment verified: {expected_revision}", flush=True)
                return True
            print(f"Attempt {attempt}: waiting for revision {expected_revision}; got {health.get('revision', 'unknown')}", flush=True)
        except Exception as exc:
            print(f"Attempt {attempt}: health check failed ({type(exc).__name__})", flush=True)
        if attempt < attempts:
            time.sleep(interval)
    print("Deployment failed: the expected revision is not healthy", flush=True)
    return False


if __name__ == "__main__":
    raise SystemExit(0 if verify_deployment(os.environ["EXPECTED_REVISION"]) else 1)
