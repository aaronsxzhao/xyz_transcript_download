"""Read-only snapshots for the two Nov11 authorized disposable imports.

Historical claim/heartbeat/drain events were not stored. These snapshots must
never be described as a reconstructed timeline or proof of a historical cause.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PREFIXES = ('c9a6a826-ac4', '3b886818-487')
SELECT = 'task_id,user_id,state,attempts,cancel_requested,worker_id,worker_group,lease_until,created_at,updated_at,deleted:payload->deleted'


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def inspect(get):
    records = []
    owners = set()
    for prefix in PREFIXES:
        rows = get('processing_work', {'select': SELECT, 'kind': 'eq.video',
            'task_id': 'eq.' + prefix, 'order': 'created_at.asc', 'limit': '21'})
        if len(rows) > 20 or any(not isinstance(row, dict) or not isinstance(row.get('task_id'), str)
                or row['task_id'] != prefix or not row.get('user_id') for row in rows):
            return {'status': 'blocked_ambiguous_or_truncated', 'production_writes': False, 'provider_calls': 0}
        owners.update(row['user_id'] for row in rows)
        if len(owners) > 1 or len({row['task_id'] for row in rows}) > 1:
            return {'status': 'blocked_ambiguous_or_truncated', 'production_writes': False, 'provider_calls': 0}
        snapshots = []
        for row in rows:
            safe = {'state': row['state'] if row.get('state') in ('queued','running','completed','failed','cancelled') else 'unknown'}
            if type(row.get('attempts')) is int and 0 <= row['attempts'] <= 1000000:
                safe['attempts'] = row['attempts']
            for key in ('cancel_requested','deleted'):
                if type(row.get(key)) is bool:
                    safe[key] = row[key]
            for key in ('created_at','updated_at','lease_until'):
                safe[key] = timestamp(row.get(key))
            if row.get('worker_group') in ('embedded','worker'):
                safe['worker_group'] = row['worker_group']
            worker = row.get('worker_id')
            if isinstance(worker,str) and re.fullmatch(r'[0-9a-f-]{36}',worker):
                safe['worker_reference'] = hashlib.sha256(worker.encode()).hexdigest()[:12]
            snapshots.append(safe)
        records.append({'task_prefix':prefix,'status':'found' if rows else 'not_found','snapshots':snapshots})
    controls = get('processing_controls', {'select':'target_revision,expires_at',
        'name':'eq.drain_embedded','limit':'2'})
    drain = []
    for row in controls:
        if isinstance(row,dict) and re.fullmatch(r'[0-9a-f]{40}',str(row.get('target_revision',''))):
            drain.append({'target_revision':row['target_revision'],'expires_at':timestamp(row.get('expires_at'))})
    return {'status':'snapshot_only','production_writes':False,'provider_calls':0,
        'tasks':records,'current_drain':drain,
        'historical_events_available':False,
        'missing_history':['enqueue_to_claim','claim_outcome','heartbeat_events','drain_intervals','dispatcher_poll_and_slot_occupancy']}


def inspect_bindings(bindings):
    base, key = bindings['SUPABASE_URL'], bindings['SUPABASE_SERVICE_KEY']
    def get(table, query):
        request = Request(base.rstrip('/')+'/rest/v1/'+table+'?'+urlencode(query),
            headers={'apikey':key,'Authorization':'Bearer '+key})
        with urlopen(request,timeout=30) as response:
            return json.load(response)
    try:
        return inspect(get)
    except Exception as error:
        return {'status':'blocked','error_type':type(error).__name__,
            'production_writes':False,'provider_calls':0}
