"""Isolated, read-only saved-provider review via existing deployment bindings.

Only encrypted generated notes leave the temporary directory. The repository
contains the review PUBLIC key; its private key never enters the runner.
"""
import base64
import contextlib
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
ROOT = Path(__file__).resolve().parents[1]
CASES = ('video:ac5c4dc6-102', 'video:a4f1b713-678', 'podcast:6a7a72b57bb1a8868fb4b2eb')


def encrypt_report(report, public_key):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key, nonce = os.urandom(32), os.urandom(12)
    associated = b'xyz-private-summary-review-v1'
    sealed = AESGCM(key).encrypt(nonce, json.dumps(report, ensure_ascii=False).encode(), associated)
    wrapped = serialization.load_pem_public_key(public_key).encrypt(key,
        padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    encode = lambda data: base64.b64encode(data).decode()
    return dict(version=1, algorithm='RSA-OAEP-SHA256+AES-256-GCM',
                wrapped_key=encode(wrapped), nonce=encode(nonce), ciphertext=encode(sealed))


def safe_failure(error):
    status = getattr(error, 'status_code', None)
    result = {'error_type': type(error).__name__}
    if type(status) is int and 100 <= status <= 599:
        result['http_status'] = status
    response = getattr(error, 'response', None)
    if response is not None:
        result['html_response'] = 'text/html' in response.headers.get('content-type', '').lower()
        reference = response.headers.get('cf-ray', '')
        if re.fullmatch(r'[A-Za-z0-9-]{1,100}', reference):
            result['reference'] = reference
    # Never include provider response text, exception messages or request headers.
    return result


def child(output):
    from api.supabase_client import get_supabase_admin_client
    from api.user_settings import get_user_settings
    from api.custom_models import probe_provider
    from source_coverage import EDITORIAL_VERSION
    database = get_supabase_admin_client()
    # Anchor this requested review to its source owner, never the first account.
    owners = database.table('transcripts').select('user_id').eq('episode_id', CASES[-1].partition(':')[2]).limit(2).execute().data or []
    if len(owners) != 1:
        raise ValueError('The requested review account is not unique.')
    owner = owners[0]['user_id']
    settings = get_user_settings(owner)
    if settings.get('llm_provider') != 'custom':
        raise ValueError('The requested account must have its custom provider selected.')
    report = {'revision': os.environ.get('GITHUB_SHA', ''), 'editorial_version': EDITORIAL_VERSION,
              'model': settings.get('llm_model'), 'base_url': settings.get('llm_base_url'),
              'saved_key_loaded': bool(settings.get('llm_api_key')),
              'saved_key_error': bool(settings.get('llm_api_key_error')),
              'preflight': [], 'samples': [], 'production_writes': False}
    ready = False
    for attempt in range(2):
        started = time.monotonic()
        try:
            probe_provider(settings, 'summary')
            report['preflight'].append({'ok': True, 'elapsed_seconds': round(time.monotonic()-started, 2)})
            ready = True
            break
        except Exception as error:
            report['preflight'].append({'ok': False, 'elapsed_seconds': round(time.monotonic()-started, 2), **safe_failure(error)})
    if ready:
        for index, case in enumerate(CASES, 1):
            directory = output / f'sample-{index}'
            started = time.monotonic()
            row = {'case': case, 'ok': False}
            try:
                result = subprocess.run([sys.executable, 'scripts/review_saved_model_samples.py',
                    '--owner', owner, '--case', case, '--output', str(directory)],
                    cwd=ROOT, capture_output=True, text=True, timeout=480)
                artifact = directory / 'case-001.json'
                if result.returncode == 0 and artifact.exists():
                    row.update(ok=True, generated=json.loads(artifact.read_text()))
                else:
                    row['error_type'] = 'GenerationFailed'
                    for line in result.stdout.splitlines():
                        try:
                            failure = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(failure, dict) and failure.get('ok') is False and failure.get('sample') == 1:
                            row['failure'] = {key:failure[key] for key in ('error','error_type') if isinstance(failure.get(key),str)}
            except subprocess.TimeoutExpired:
                row['error_type'] = 'SampleDeadlineExceeded'
            checkpoint = directory / 'progress.json'
            if checkpoint.exists():
                row['progress'] = json.loads(checkpoint.read_text())
            row['elapsed_seconds'] = round(time.monotonic()-started, 2)
            report['samples'].append(row)
    report['halted_after_connection_test'] = not ready
    output.joinpath('report.json').write_text(json.dumps(report, ensure_ascii=False))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                child(Path(sys.argv[2]))
            except Exception as error:
                Path(sys.argv[2], 'report.json').write_text(json.dumps({
                    'infrastructure_failed': True, 'production_writes': False, **safe_failure(error)}))
        return 0
    from scripts.diagnose_deployment import oci_json
    report = {'infrastructure_failed': True, 'production_writes': False}
    with tempfile.TemporaryDirectory() as name:
        output = Path(name)
        containers = oci_json(['container-instances', 'container-instance', 'get',
            '--container-instance-id', os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"')
        bindings = None
        for container in containers or []:
            candidate = oci_json(['container-instances', 'container', 'get', '--container-id', container], 'data."environment-variables"') or {}
            if candidate.get('SUPABASE_URL') and candidate.get('SUPABASE_SERVICE_KEY'):
                bindings = {key:value for key,value in candidate.items() if key.startswith('SUPABASE_') or key in {'USE_SUPABASE', 'MODEL_CREDENTIAL_KEY'}}
                break
        if bindings:
            environment = {**os.environ, **bindings, 'XYZ_DATA_DIR': name,
                           'DISCORD_WEBHOOK_URL': '', 'WHISPER_MODE': 'api', 'PYTHONPATH': '.'}
            result = subprocess.run([sys.executable, __file__, '--child', name], env=environment,
                                    capture_output=True, text=True, timeout=1500)
            if result.returncode == 0 and output.joinpath('report.json').exists():
                report = json.loads(output.joinpath('report.json').read_text())
        destination = Path('/tmp/xyz-review-artifacts')
        destination.mkdir(mode=0o700, exist_ok=True)
        envelope = encrypt_report(report, ROOT.joinpath('scripts/sample_review_public.pem').read_bytes())
        serialized = json.dumps(envelope)
        destination.joinpath('review.enc.json').write_text(serialized)
        # A ciphertext-only log transport also lets the authorized reviewer
        # retrieve results when an artifact download integration is unavailable.
        chunks = [serialized[i:i+2048] for i in range(0, len(serialized), 2048)]
        for index, chunk in enumerate(chunks):
            print(f'XYZ_REVIEW_CHUNK {index+1}/{len(chunks)} {chunk}', flush=True)
    print(json.dumps({'review_finished': not report.get('infrastructure_failed', False),
                      'provider_ready': not report.get('halted_after_connection_test', True),
                      'samples_completed': sum(row['ok'] for row in report.get('samples', [])),
                      'encrypted_artifact': True, 'production_writes': False}))
    return int(bool(report.get('infrastructure_failed')))


if __name__ == '__main__':
    raise SystemExit(main())
