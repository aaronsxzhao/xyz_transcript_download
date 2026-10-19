"""Production diagnostics must not publish arbitrary log or health contents."""
from scripts.diagnose_deployment import safe_health, safe_log_summary


def test_diagnostics_whitelist_startup_failures():
    text = '''Authorization: Bearer super-secret-value
  File "/app/api/main.py", line 17, in <module>
ModuleNotFoundError: No module named 'missing_dependency'
ValueError: password=do-not-publish
'''
    summary = safe_log_summary(text)
    assert summary["missing_modules"] == ["missing_dependency"]
    assert summary["source_frames"] == [{"file": "/app/api/main.py", "line": 17}]
    assert "ValueError" in summary["exception_types"]
    assert "super-secret-value" not in str(summary)
    assert "do-not-publish" not in str(summary)


def test_diagnostics_only_report_public_health_fields():
    assert safe_health(b'{"status":"ok","revision":"unknown","token":"secret"}') == {"status":"ok", "revision":"unknown"}
    assert safe_health(b'{"revision":"private-value","password":"secret"}') == {}
    assert safe_health(b'invalid json') == {}
