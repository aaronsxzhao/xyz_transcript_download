"""One-time, backed-up repair of the two explicitly reported reading notes.

Generate from saved transcripts only. Private source, old/new notes and provenance
stay in application-backups; CI receives numeric diagnostics, never source text.
No audio download, retranscription, account settings or notifications are changed.
"""
import contextlib
from dataclasses import asdict
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_coverage import EDITORIAL_VERSION

TARGETS = ((138, "6ad6a22b336a696d21590ba6"), (137, "6ad0a61f0e4e410a05bd5f13"))
BUCKET = "application-backups"
_PHASE = 0


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def note_content(note):
    row = asdict(note)
    return {key: row[key] for key in ("episode_id", "title", "overview", "topics", "takeaways", "key_points")}


def verified_upload(storage, path, value):
    content = encoded(value)
    storage.upload(path, content, file_options={"content-type": "application/json", "upsert": "false"})
    if storage.download(path) != content:
        raise RuntimeError("Private repair backup verification failed")


def repair():
    global _PHASE
    from api.supabase_db import SupabaseDatabase
    from api.user_settings import get_user_settings
    from api.llm_settings import resolve_llm_settings
    from summarizer import Summarizer
    from transcriber import Transcript, TranscriptSegment
    db = SupabaseDatabase()
    _PHASE = 1
    bucket = db.client.storage.get_bucket(BUCKET)
    public = bucket.get("public", False) if isinstance(bucket, dict) else getattr(bucket, "public", False)
    if public:
        raise RuntimeError("Repair backup bucket must be private")
    storage = db.client.storage.from_(BUCKET)
    report = {"operation": "coverage_repair", "repaired": 0, "already_repaired": 0, "source_unchanged": 0}
    for summary_id, episode_id in TARGETS:
        rows = db.client.table("summaries").select("user_id").eq("id", summary_id).eq("episode_id", episode_id).execute().data
        if len(rows) != 1:
            raise RuntimeError("Reported note ownership unavailable")
        owner = rows[0]["user_id"]
        original = db.get_summary(owner, episode_id)
        source = db.get_transcript(owner, episode_id)
        if not original or not source:
            raise RuntimeError("Reported source unavailable")
        source_hash = digest(asdict(source))
        prefix = f"reading-repairs/{owner}/{episode_id}/{EDITORIAL_VERSION}-{source_hash}"
        # List by a fixed manifest filename; never mistake a network failure
        # downloading a marker for permission to regenerate.
        objects = storage.list(prefix, {"search": "complete.json", "limit": 10})
        if any(item.get("name") == "complete.json" for item in objects):
            marker = json.loads(storage.download(prefix + "/complete.json"))
            if marker.get("source_hash") != source_hash:
                raise RuntimeError("Repair receipt source mismatch")
            report["already_repaired"] += 1
            continue
        active = (db.client.table("processing_jobs").select("id,payload")
                  .eq("user_id", owner).eq("payload->>episode_id", episode_id)
                  .in_("payload->>status", ["pending", "fetching", "downloading", "transcribing", "summarizing"])
                  .execute().data)
        if active:
            raise RuntimeError("Reported note has an active task; retry maintenance later")
        original_content = note_content(original)
        # Immutable per-run backup is verified BEFORE generating or writing.
        attempt = os.environ.get("GITHUB_RUN_ID", "manual") + "-" + os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        backup_path = prefix + f"/{attempt}-before.json"
        _PHASE = 2
        verified_upload(storage, backup_path, {"source": asdict(source), "summary": asdict(original), "source_hash": source_hash})
        settings = resolve_llm_settings(get_user_settings(owner))
        engine = Summarizer(**settings)
        transcript = Transcript(source.episode_id, source.language, source.duration, source.text,
                                [TranscriptSegment(s["start"], s["end"], s["text"]) for s in source.segments])
        _PHASE = 3
        candidate = engine.summarize(transcript, episode_title=original.title, existing_topics=original.topics)
        if not candidate or not candidate.key_points:
            raise RuntimeError("Source-reviewed generation did not complete")
        candidate_content = note_content(candidate)
        _PHASE = 4
        verified_upload(storage, prefix + f"/{attempt}-candidate.json", {
            "summary": candidate_content, "source_hash": source_hash, "editorial_version": EDITORIAL_VERSION,
            "source_revision": os.environ.get("GITHUB_SHA", "manual"), "model": engine.model})
        # Never overwrite an intervening edit or a changed source.
        _PHASE = 5
        if digest(asdict(db.get_transcript(owner, episode_id))) != source_hash:
            raise RuntimeError("Source changed during repair")
        if note_content(db.get_summary(owner, episode_id)) != original_content:
            raise RuntimeError("Note changed during repair")
        _PHASE = 6
        if not db.save_summary(owner, **candidate_content):
            raise RuntimeError("Reviewed note save failed")
        _PHASE = 7
        saved = note_content(db.get_summary(owner, episode_id))
        # JSON-FK ordering is not guaranteed; compare all point bodies/evidence
        # without treating row order as proof of lost information.
        canonical = lambda value: {**value, "key_points": sorted(value["key_points"], key=lambda p: json.dumps(p, sort_keys=True))}
        if canonical(saved) != canonical(candidate_content):
            raise RuntimeError("Reviewed note readback failed; private backup retained")
        _PHASE = 8
        verified_upload(storage, prefix + "/complete.json", {
            "source_hash": source_hash, "note_hash": digest(saved), "backup_path": backup_path,
            "editorial_version": EDITORIAL_VERSION, "source_revision": os.environ.get("GITHUB_SHA", "manual")})
        report["repaired"] += 1
        report["source_unchanged"] += 1
    return report


def main():
    from scripts.diagnose_deployment import oci_json
    from scripts.repair_reported_transcript import request_json
    expected = os.environ.get("EXPECTED_REVISION")
    if expected and request_json("/api/health", "").get("revision") != expected:
        raise RuntimeError("Expected release is not live")
    containers = oci_json(["container-instances", "container-instance", "get", "--container-instance-id", os.environ["CONTAINER_INSTANCE_ID"]], 'data.containers[*]."container-id"')
    for container_id in containers or []:
        bindings = oci_json(["container-instances", "container", "get", "--container-id", container_id], 'data."environment-variables"') or {}
        if not bindings.get("SUPABASE_SERVICE_KEY"):
            continue
        # Bindings are used only in memory; never print them or pass via argv.
        os.environ.update({k: v for k, v in bindings.items() if k.startswith("SUPABASE_") or k in {"USE_SUPABASE", "GROQ_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"}})
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            os.environ["XYZ_DATA_DIR"] = directory
            os.environ["WHISPER_MODE"] = "api"
            logging.disable(logging.CRITICAL)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return repair()
    raise RuntimeError("Private application bindings unavailable")


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as error:
        print(json.dumps({"operation": "coverage_repair", "failed": 1, "phase": _PHASE, "error_type": type(error).__name__}))
        sys.exit(1)
