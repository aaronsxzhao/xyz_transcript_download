"""Public app bootstrap data and route preloads, available with the HTML."""
import json
import re
from functools import lru_cache
from pathlib import Path


def page_name(path: str) -> str:
    if path.startswith("podcasts/"):
        return "Episodes"
    if path.startswith("viewer/"):
        return "Viewer"
    if path.startswith("videos/"):
        return "VideoViewer"
    return {"podcasts": "Podcasts", "videos": "Videos", "library": "Library", "settings": "Settings", "login": "Login", "reset-password": "ResetPassword"}.get(path, "Dashboard")


def frontend_html(directory: Path, path: str, auth_enabled: bool, supabase_url: str) -> str:
    index = directory / "index.html"
    manifest = directory / "manifest.json"
    return _render(str(directory), index.stat().st_mtime_ns,
                   manifest.stat().st_mtime_ns if manifest.exists() else 0,
                   page_name(path), auth_enabled, supabase_url)


@lru_cache(maxsize=16)
def _render(directory: str, index_stamp: int, manifest_stamp: int, page: str,
            auth_enabled: bool, supabase_url: str) -> str:
    root = Path(directory)
    html = (root / "index.html").read_text(encoding="utf-8")
    config = json.dumps({"supabase_enabled": auth_enabled,
                         "supabase_url": supabase_url if auth_enabled else None}).replace("<", "\\u003c")
    additions = [f'<script type="application/json" id="xyz-auth-config">{config}</script>']
    if manifest_stamp:
        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        except (ValueError, OSError):
            manifest = {}
        embedded=set()
        def collect_static(key):
            entry=manifest.get(key,{})
            file=entry.get('file','')
            if not file or file in embedded:return
            embedded.add(file)
            embedded.update(entry.get('css',[]))
            for dependency in entry.get('imports',[]):collect_static(dependency)
        collect_static('index.html')
        visited = set()
        def preload(key):
            if key in visited:
                return
            visited.add(key)
            entry = manifest.get(key, {})
            for asset in [entry.get("file", ""), *entry.get("css", [])]:
                if not re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(js|css)", asset) or asset in embedded or re.search(r'(?:src|href)="/'+re.escape(asset)+r'"',html):
                    continue
                # Fetch route bytes early without resolving its imports before
                # the document installs the shared-runtime import map.
                rel = 'rel="stylesheet"' if asset.endswith('.css') else 'rel="preload" as="script"'
                additions.append(f'<link {rel} href="/{asset}" crossorigin>')
            for dependency in entry.get("imports", []):
                preload(dependency)
        key=f"src/pages/{page}.tsx"
        # Explicit Vite chunk groups use generated manifest keys instead of the
        # source path. Preload the selected route in parallel with the document.
        if key not in manifest:
            key=next((key for key,entry in manifest.items() if entry.get('name')==page and entry.get('file','').endswith('.js')),key)
        preload(key)
    return html.replace("</head>", "\n".join(additions) + "\n</head>")
