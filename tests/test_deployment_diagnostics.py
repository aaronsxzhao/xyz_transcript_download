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


def test_library_profile_never_logs_credentials_or_arbitrary_child_output(capsys):
    import json
    from types import SimpleNamespace
    from unittest.mock import patch
    from scripts.diagnose_deployment import profile_library
    output = json.dumps({"library_profile": "video_note", "status": 200, "milliseconds": 12,
                         "api_key": "secret-value", "content": "private-note"})
    with patch("scripts.diagnose_deployment.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=output)):
        profile_library({"SUPABASE_SERVICE_KEY": "secret-value", "UNRELATED_SECRET": "private-note"})
    text = capsys.readouterr().out
    assert "secret-value" not in text and "private-note" not in text
    assert json.loads(text) == {"library_profile": "video_note", "status": 200, "milliseconds": 12}


def test_public_probes_only_get_and_keep_credentials_out_of_arguments(monkeypatch):
    import json
    from types import SimpleNamespace
    from scripts.profile_library import profile_public_routes
    calls = []
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "private-signing-secret-for-profiling-only")
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps({"http_code": 200, "time_total": .25,
                                                  "time_starttransfer": .2, "size_download": 123}))
    monkeypatch.setattr("scripts.profile_library.subprocess.run", run)
    reports = profile_public_routes("private-owner", [("podcasts", "/api/podcasts"), ("settings", "/api/settings")])
    assert [r["library_profile"] for r in reports] == ["live_auth", "live_podcasts", "live_settings"]
    assert all(r["status"] == 200 and r["milliseconds"] == 250 for r in reports)
    for command, kwargs in calls:
        assert "--data" not in command and "--request" not in command
        assert command[-1].startswith("https://aipodcastsummary.online/api/")
        assert "Bearer" not in str(command) and "private-signing-secret" not in str(command)
        assert kwargs["input"].startswith("Authorization: Bearer ")
    assert "private-owner" not in str(reports) and "Bearer" not in str(reports)


def test_summary_failure_diagnostics_emit_only_counts():
    report = safe_log_summary('Summary response was incomplete (length). secret-key private content\nIndexError: list index out of range')
    assert report['summary_failures']['output_limit'] == 1
    assert report['summary_failures']['empty_choices'] == 1
    assert 'secret-key' not in str(report)


def test_audit_issue_counts_do_not_include_private_source_or_unknown_labels():
    report=safe_log_summary('Delivering video draft after audit failure: invalid_note_reference\nDelivering draft after audit failure: missing_units\nDelivering draft after audit failure: secret-token')
    assert report['summary_audit_issues']['invalid_note_reference']==1
    assert report['summary_audit_issues']['missing_units']==1
    assert 'secret-token' not in str(report)
