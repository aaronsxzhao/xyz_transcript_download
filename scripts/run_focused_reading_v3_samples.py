"""One-time authorized comparison using the focused-reading-v3 candidate pipeline. Never writes production data."""
import base64
import contextlib
import gzip
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CASES = (
    ('video', '7966585c-6a1', 'en', 600, 800),
    ('podcast', '6aaa0b81051af796b9e8e897', 'zh', 3000, 3500),
    ('video', 'daf7961d-966', 'en', 3000, 4000),
)

def count_text(text, language):
    return len(re.findall(r'[\u3400-\u9fff]', text)) if language == 'zh' else len(re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?", text))


def one(database, owner, spec, settings):
    from openai import OpenAI
    from api.custom_models import custom_http_client
    from source_coverage import video_source_text, spoken_source, quote_timestamp
    from summary_format import extract_model_json
    from scripts.run_production_sample_review import safe_failure
    kind, identifier, language, minimum, maximum = spec
    row = {'kind': kind, 'id': identifier, 'language': language, 'ok': False,
           'budget': {'minimum': minimum, 'maximum': maximum, 'unit': 'Chinese characters' if language == 'zh' else 'English words'}}
    started = time.monotonic()
    if kind == 'video':
        saved = database.table('video_tasks').select('title,duration,markdown,transcript_json,model,url').eq('user_id', owner).eq('id', identifier).single().execute().data
        transcript = json.loads(saved.get('transcript_json') or '{}')
        text = transcript.get('text') or ''
        segments = transcript.get('segments') or []
        baseline = {'markdown': saved.get('markdown') or '', 'model': saved.get('model') or '', 'url': saved.get('url') or ''}
        duration = saved.get('duration') or transcript.get('duration') or 0
    else:
        saved = database.table('summaries').select('title,overview,topics,takeaways,summary_key_points(id,topic,summary,original_quote,timestamp)').eq('user_id', owner).eq('episode_id', identifier).single().execute().data
        transcript = database.table('transcripts').select('id,text,duration').eq('user_id', owner).eq('episode_id', identifier).single().execute().data
        text = transcript.get('text') or ''
        segments = []
        offset = 0
        while True:
            page = database.table('transcript_segments').select('start_time,text').eq('transcript_id', transcript['id']).order('start_time').range(offset, offset + 999).execute().data or []
            segments.extend({'start': part['start_time'], 'text': part['text']} for part in page)
            if len(page) < 1000:
                break
            offset += len(page)
        baseline = {key: saved.get(key) for key in ('overview', 'topics', 'takeaways', 'summary_key_points')}
        duration = transcript.get('duration') or 0
    if not text.strip():
        raise ValueError('The owned sample has no saved transcript')
    source = video_source_text(text, segments)
    row.update(title=saved['title'], duration_seconds=duration, baseline=baseline,
               source_text=text, submitted_source=source, source_chars=len(text),
               source_units=count_text(text, language), source_sha256=hashlib.sha256(text.encode()).hexdigest(),
               submitted_source_chars=len(source), full_source_submitted=True)
    from dataclasses import asdict
    from processing_execution import Execution, bind
    from execution_store import Store
    from reading_generation import VERSION
    from note_summarizer import NoteSummarizer
    from summarizer import Summarizer
    from transcriber import Transcript, TranscriptSegment
    engine = None
    try:
        # Ephemeral LOCAL checkpoints allow production-like bounded concurrency;
        # no queue row, summary, settings or checkpoint is written to Supabase.
        with tempfile.TemporaryDirectory() as directory:
            execution = Execution(owner, identifier, Store(path=Path(directory)/'checkpoints.sqlite'))
            with bind(execution):
                if kind == 'video':
                    engine = NoteSummarizer(**settings)
                    generated = engine.generate_note(saved['title'], source, style='detailed',
                        formats=['toc','summary','link','screenshot'], duration=duration)
                else:
                    engine = Summarizer(**settings)
                    parts = [TranscriptSegment(float(part['start']),
                        float(segments[i+1]['start']) if i+1<len(segments) else duration,
                        part['text']) for i,part in enumerate(segments)]
                    generated = engine.summarize(Transcript(identifier,language,duration,text,parts),
                        episode_title=saved['title'], existing_topics=saved.get('topics') or [])
                row['generated'] = asdict(generated) if kind == 'podcast' and generated else generated
                row['ok'] = bool(generated)
                row['prompt_version'] = VERSION
                row['generation_report'] = engine.generation_report
                row['runtime'] = execution.snapshot()
        if kind == 'podcast' and generated:
            row['quote_checks'] = [{'verbatim':bool(p.original_quote.strip()) and
                re.sub(r'\s+','',p.original_quote) in re.sub(r'\s+','',text),
                'timestamp':p.timestamp} for p in generated.key_points]
    except Exception as error:
        row['failure'] = safe_failure(error)
    finally:
        if engine is not None:
            row['generation_report'] = getattr(engine,'generation_report',{})
            engine.client.close()
    row['elapsed_seconds'] = round(time.monotonic() - started, 2)
    return row


def child(output):
    from api.supabase_client import get_supabase_admin_client
    from api.user_settings import get_user_settings
    from api.llm_settings import resolve_llm_settings
    from concurrent.futures import ThreadPoolExecutor
    database = get_supabase_admin_client()
    owners = database.table('video_tasks').select('user_id').eq('id', 'bc2c988b-2b4').limit(2).execute().data or []
    if len(owners) != 1:
        raise ValueError('Requested source owner unavailable')
    owner = owners[0]['user_id']
    preferences = get_user_settings(owner)
    if preferences.get('llm_provider') != 'custom':
        raise ValueError('The saved custom provider selection changed; no provider fallback is allowed')
    settings = resolve_llm_settings(preferences)
    report = {'production_writes': False, 'comparison': 'saved_existing_A_vs_new_full_source_B',
              'model': settings['model'], 'provider': 'saved_custom', 'model_options': settings.get('model_options', {}),
              'tested_revision':os.environ.get('GITHUB_SHA',''), 'prompt_version':'focused-reading-v3', 'source_scope': 'complete_saved_transcripts', 'samples': []}
    # Separate DB clients avoid sharing request sessions across independent cases.
    def generate(spec):
        try:
            result = one(get_supabase_admin_client(), owner, spec, settings)
            output.joinpath(spec[1]+'.json').write_text(json.dumps(result,ensure_ascii=False))
            return result
        except Exception as error:
            from scripts.run_production_sample_review import safe_failure
            return {'kind': spec[0], 'id': spec[1], 'ok': False, 'failure': safe_failure(error)}
    with ThreadPoolExecutor(max_workers=2) as pool:
        report['samples'] = list(pool.map(generate, CASES))
    output.joinpath('report.json').write_text(json.dumps(report, ensure_ascii=False))


def main():
    from scripts.run_production_sample_review import encrypt_report, safe_failure
    if '--child' in sys.argv:
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                child(Path(sys.argv[-1]))
            except Exception as error:
                Path(sys.argv[-1], 'report.json').write_text(json.dumps({'infrastructure_failed': True, 'production_writes': False, **safe_failure(error)}))
        return
    from scripts.diagnose_deployment import oci_json
    report = {'infrastructure_failed': True, 'production_writes': False}
    with tempfile.TemporaryDirectory() as name:
        output = Path(name)
        containers = oci_json(['container-instances', 'container-instance', 'get', '--container-instance-id', os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"') or []
        for container in containers:
            candidate = oci_json(['container-instances', 'container', 'get', '--container-id', container], 'data."environment-variables"') or {}
            if not candidate.get('SUPABASE_URL') or not candidate.get('SUPABASE_SERVICE_KEY'):
                continue
            bindings = {key: value for key, value in candidate.items() if key.startswith('SUPABASE_') or key in {'USE_SUPABASE', 'MODEL_CREDENTIAL_KEY'}}
            environment = {**os.environ, **bindings, 'XYZ_DATA_DIR': name, 'DISCORD_WEBHOOK_URL': '', 'WHISPER_MODE': 'api', 'PYTHONPATH': '.'}
            try:
                subprocess.run([sys.executable, __file__, '--child', name], env=environment, capture_output=True, text=True, timeout=3000)
                if output.joinpath('report.json').exists():
                    report = json.loads(output.joinpath('report.json').read_text())
            except Exception as error:
                report.update(safe_failure(error))
                partial = [json.loads(path.read_text()) for path in output.glob('*.json') if path.name != 'report.json']
                if partial:
                    report.update(samples=partial, incomplete_run=True)
            break
        packed = base64.b64encode(gzip.compress(json.dumps(report, ensure_ascii=False).encode())).decode()
        envelope = encrypt_report({'compression': 'gzip-base64', 'report': packed}, Path('scripts/sample_review_public.pem').read_bytes())
        destination = Path('/tmp/xyz-review-artifacts'); destination.mkdir(mode=0o700, exist_ok=True)
        serialized = json.dumps(envelope)
        destination.joinpath('focused-reading-v3-samples.enc.json').write_text(serialized)
    print(json.dumps({'review_finished': not report.get('infrastructure_failed', False), 'samples_completed': sum(bool(row.get('ok')) for row in report.get('samples', [])), 'encrypted_artifact': True, 'production_writes': False}))


if __name__ == '__main__':
    main()
