"""Wait until the public API serves the expected healthy application revision."""
import json
import os
import time
import urllib.request


def verify_deployment(expected_revision: str, attempts: int = 18, interval: int = 10) -> bool:
    url = f"https://aipodcastsummary.online/api/health?revision={expected_revision}"
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=10) as response:
                health = json.load(response)
            if health.get("status") == "ok" and health.get("revision") == expected_revision:
                print(f"Deployment verified: {expected_revision}")
                return True
            print(f"Attempt {attempt}: waiting for revision {expected_revision}; got {health.get('revision', 'unknown')}")
        except Exception as exc:
            print(f"Attempt {attempt}: health check failed ({type(exc).__name__})")
        if attempt < attempts:
            time.sleep(interval)
    print("Deployment failed: the expected revision is not healthy")
    return False


if __name__ == "__main__":
    raise SystemExit(0 if verify_deployment(os.environ["EXPECTED_REVISION"]) else 1)
