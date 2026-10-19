"""Cold navigations should receive public config and the requested route together."""
import json

from api.frontend import frontend_html


def test_route_preloads_only_current_page_and_static_dependencies(tmp_path):
    (tmp_path / "index.html").write_text('<html><head><script src="/assets/app-123.js"></script></head></html>')
    manifest = {
        "src/pages/Episodes.tsx": {"file": "assets/Episodes-123.js", "imports": ["runtime"], "css": ["assets/Episodes-123.css"]},
        "src/pages/Viewer.tsx": {"file": "assets/Viewer-123.js"},
        "runtime": {"file": "assets/app-123.js", "imports": ["runtime"]},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    html = frontend_html(tmp_path, "podcasts/private-id/episodes", True, "https://example.supabase.co")
    assert html.count('/assets/app-123.js') == 1
    assert 'rel="modulepreload" href="/assets/Episodes-123.js"' in html
    assert 'rel="stylesheet" href="/assets/Episodes-123.css"' in html
    assert "Viewer-123.js" not in html and "private-id" not in html
    config = html.split('id="xyz-auth-config">')[1].split('</script>')[0]
    assert json.loads(config) == {"supabase_enabled": True, "supabase_url": "https://example.supabase.co"}


def test_bootstrap_contains_no_credentials_and_escapes_inline_data(tmp_path):
    (tmp_path / "index.html").write_text('<html><head></head></html>')
    html = frontend_html(tmp_path, "viewer/anything", True, '</script><script>alert(1)</script>')
    assert html.count('</script>') == 1 and "\\u003c/script>" in html
    local = frontend_html(tmp_path, "videos", False, "not-public-in-local-mode")
    assert '"supabase_enabled": false' in local and '"supabase_url": null' in local
    assert "not-public-in-local-mode" not in local
