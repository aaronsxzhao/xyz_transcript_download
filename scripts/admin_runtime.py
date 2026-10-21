"""Run maintenance with the existing deployment bindings, without logging them."""
import json
import os
import subprocess
import sys
import tempfile
from scripts.diagnose_deployment import oci_json


def run_private_child(script, timeout=1800):
    containers = oci_json(['container-instances', 'container-instance', 'get', '--container-instance-id',
                           os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"')
    if not containers:
        raise RuntimeError('Deployment unavailable')
    bindings = None
    for container_id in containers:
        candidate = oci_json(['container-instances', 'container', 'get', '--container-id', container_id],
                             'data."environment-variables"') or {}
        if candidate.get('SUPABASE_URL') and candidate.get('SUPABASE_SERVICE_KEY'):
            bindings = candidate
            break
    if not bindings:
        raise RuntimeError('Application database bindings unavailable')
    environment = {**os.environ, **{k: v for k, v in bindings.items() if k.startswith('SUPABASE_')},
                   'WHISPER_MODE': 'api', 'SUPABASE_STORAGE_ENABLED': 'true'}
    with tempfile.TemporaryDirectory() as directory:
        environment['XYZ_DATA_DIR'] = directory
        result = subprocess.run([sys.executable, script, '--child'], env=environment,
                                capture_output=True, text=True, timeout=timeout)
    # Child output is a fixed-label numeric report. Never forward raw logs.
    reports = []
    for line in result.stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get('operation') in {'backup', 'media_recovery', 'publication_dates'}:
            reports.append({k: v for k, v in row.items() if k == 'operation' or type(v) is int})
    for row in reports:
        print(json.dumps(row), flush=True)
    return result.returncode if reports else 1
