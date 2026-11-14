"""Read-only, allowlisted diagnostics for the two authorized failed test jobs.

Uses existing deployment bindings in memory. Emits no owner IDs, source text,
provider settings, credentials, raw exceptions or raw model responses.
"""
import json
import math
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TASKS = ('25b33b27-b86e-442b-90f3-10473289c252', 'cdbe3c1e-1d8f-4ee4-8e2f-792907535b48')
COUNTERS = ('coverage_ratio', 'coverage_threshold', 'threshold', 'failed_batches',
    'inventory_failed_batches', 'inventory_validation_failed_batches', 'ignored_boundary_items',
    'terminal_provider_failure', 'grounding_concerns', 'unresolved_items', 'covered_items',
    'requests', 'validation_retries', 'repairs_accepted', 'repairs_rejected',
    'inventory_transport_retries', 'inventory_split_retries', 'inventory_recovered_batches', 'inventory_batches', 'reviewed', 'review_attempts', 'review_parts', 'final_coverage_attempts')

ROUND_PHASES = ('initial','resume','after_grounding_repair','final_coverage_repair')
ROUND_KINDS = ('claim','experiment','counterexample','condition','disagreement','procedure','example')
ROUND_STATUSES = ('covered','missing','partial','contradicted','unverified','context_only')
REJECTION_REASONS = ('existing_support_regressed','no_matching_support','contradicted',
    'ungrounded','still_partial_or_missing','no_prior_gap_improved',
    'duplicate_or_no_novelty','joint_dependency_rejected')


def safe_rounds(value):
    if not isinstance(value, list): return [], False
    result=[]
    for entry in value[:50]:
        if not isinstance(entry, dict): continue
        row={}
        if entry.get('phase') in ROUND_PHASES: row['phase']=entry['phase']
        if entry.get('outcome') in ('completed','interrupted'): row['outcome']=entry['outcome']
        if entry.get('status') in ('blocked','accepted','acceptable','unverified','model_reviewed','failed'): row['status']=entry['status']
        if type(entry.get('cancelled')) is bool: row['cancelled']=entry['cancelled']
        for key in ('seconds','initial_unresolved','final_unresolved','accepted_paragraphs',
                    'rejected_paragraphs','source_corrected_items','logical_requests_reported','coverage_ratio'):
            number=entry.get(key)
            if type(number) in (int,float) and math.isfinite(number) and 0<=number<=1000000:
                row[key]=number
        for key, allowed in (('status_counts',ROUND_STATUSES), ('unresolved_by_kind',ROUND_KINDS),
                             ('rejection_reasons',REJECTION_REASONS)):
            counts=entry.get(key)
            if isinstance(counts,dict):
                row[key]={k:counts[k] for k in allowed if type(counts.get(k)) is int and 0<=counts[k]<=1000000}
        result.append(row)
    return result, len(value)>50

def safe_report(report):
    report = report if isinstance(report, dict) else {}
    safe = {}
    if type(report.get('late_contradiction_repair_attempts')) is int and 0 <= report['late_contradiction_repair_attempts'] <= 1:
        safe['late_contradiction_repair_attempts'] = report['late_contradiction_repair_attempts']
    if report.get('late_contradiction_repair_origin') in ('following_review_repair','same_delivery_iteration'):
        safe['late_contradiction_repair_origin'] = report['late_contradiction_repair_origin']
    if 'coverage_rounds' in report:
        safe['coverage_rounds'], safe['coverage_rounds_truncated'] = safe_rounds(report['coverage_rounds'])
    for key in ('delivery', 'coverage_ledger', 'verification'):
        source = report.get(key) or {}
        if not isinstance(source, dict): continue
        row = {k:source[k] for k in COUNTERS if type(source.get(k)) in (int, float, bool)
               and math.isfinite(source[k])}
        if source.get('status') in ('blocked','accepted','acceptable','unverified','model_reviewed','failed'):
            row['status'] = source['status']
        if source.get('reason') in ('coverage','source_review','grounding','review','ValueError','SummaryOutputError','ReadingProviderError'):
            row['reason'] = source['reason']
        if key == 'coverage_ledger':
            row['inventory_error_types'] = {name:sum(isinstance(e,dict) and e.get('error_type')==name for e in source.get('inventory_failures',[]) or []) for name in ('ValueError','SummaryOutputError','APIConnectionError','APITimeoutError','TimeoutError','APIStatusError','RateLimitError','RuntimeError','ReadTimeout','ConnectError','ConnectionError','ModelRequestTimeout','InternalServerError','BadRequestError','AuthenticationError','PermissionDeniedError','NotFoundError','UnprocessableEntityError')}
            row['inventory_http_statuses'] = {str(code):sum(isinstance(e,dict) and e.get('http_status')==code for e in source.get('inventory_failures',[]) or []) for code in (408,429,500,502,503,504,524)}
            row['inventory_failures_recorded'] = len(source.get('inventory_failures',[]) or [])
            row['inventory_failures_available'] = 'inventory_failures' in source
            row['item_status_counts'] = {state:sum(isinstance(i,dict) and i.get('status')==state for i in source.get('items',[]) or [])
                for state in ('covered','missing','partial','contradicted','unverified','context_only')}
        safe[key] = row
    return safe


# User supplied this exact episode for read-only latency diagnosis on 2026-11-13.
REPORTED_EPISODE = 'https://www.xiaoyuzhoufm.com/episode/6ac6a657e742e36efcbf74af'

def inspect_reported_episode(get):
    rows = get('processing_work', {
        'select':'task_id,user_id,state,attempts,metrics,created_at,updated_at',
        'kind':'eq.podcast','payload->>episode_url':'eq.'+REPORTED_EPISODE,
        'order':'created_at.desc','limit':'21'})
    if len(rows)>20 or len({row.get('user_id') for row in rows})>1:
        return {'status':'blocked_ambiguous_or_truncated','record_count':len(rows)}
    allowed = {'model.editor','transcription.segment','reading.candidate.v1',
        *('model.phase.'+phase for phase in ('draft','grounding','inventory','match','repair','validate_inventory','repair_grounding','other'))}
    result=[]
    for row in rows:
        metrics=row.get('metrics') or {}
        phases={name:{key:value for key,value in values.items()
            if key in ('seconds','calls','failed_calls') and type(value) in (int,float)
            and math.isfinite(value) and value>=0}
            for name,values in (metrics.get('stages') or {}).items()
            if name in allowed and isinstance(values,dict)}
        item={'task_id':row['task_id'],
            'state':row.get('state') if row.get('state') in ('completed','failed','cancelled','queued','running') else 'unknown',
            'stages':phases,'generation':safe_report(metrics.get('generation'))}
        for key in ('wall_seconds','checkpoint_hits'):
            value=metrics.get(key)
            if type(value) in (int,float) and math.isfinite(value) and value>=0:item[key]=value
        for key in ('created_at','updated_at'):
            value=row.get(key)
            # Dates are stored as server numeric epochs or ISO timestamps.
            if type(value) in (int,float) and math.isfinite(value):item[key]=value
        result.append(item)
    return {'status':'found' if rows else 'not_found','task_count':len(result),
            'production_writes':False,'provider_calls':0,'tasks':result}


def inspect(base, key, credential_seed=None):
    def get(table, query):
        request = Request(base.rstrip('/')+'/rest/v1/'+table+'?'+urlencode(query),
            headers={'apikey':key,'Authorization':'Bearer '+key})
        with urlopen(request, timeout=30) as response: return json.load(response)
    rows = get('processing_work', {'select':'task_id,user_id,source_id,state,attempts,metrics',
        'kind':'eq.podcast','task_id':'in.('+','.join(TASKS)+')','limit':'10'})
    if len({r['user_id'] for r in rows}) > 1: raise ValueError('Ambiguous owner')
    result = []
    for row in rows:
        item = {'task_id':row['task_id'], 'state':row['state'] if row['state'] in ('completed','failed','cancelled','queued','running') else 'unknown',
                'attempts':row.get('attempts'), 'generation':safe_report((row.get('metrics') or {}).get('generation'))}
        checkpoints = get('processing_checkpoints', {'select':'result', 'user_id':'eq.'+row['user_id'],
            'source_id':'eq.'+row['source_id'], 'stage':'eq.reading.candidate.v1','limit':'10'})
        item['candidate_checkpoints'] = [safe_report((c.get('result') or {}).get('report')) for c in checkpoints]
        item['inventory_receipts'] = [safe_report({'coverage_ledger':(c.get('result') or {}).get('inventory',[{}])[0]}) for c in checkpoints if (c.get('result') or {}).get('inventory')]
        item['candidate_count'] = len(checkpoints)
        result.append(item)
    budget = {'status':'not_checked'}
    if credential_seed and rows:
        owner = rows[0]['user_id']
        settings = get('user_settings', {'select':'preferences','user_id':'eq.'+owner,'limit':'1'})
        active = get('processing_work', {'select':'state','state':'in.(queued,running)','limit':'1000'})
        try:
            prefs = settings[0]['preferences'] if settings else {}
            budget = inspect_budget(prefs, owner, credential_seed)
        except Exception as error:
            budget = {'status':'blocked','error_type':type(error).__name__,
                      'http_status':getattr(error,'code',None) if isinstance(getattr(error,'code',None),int) else None}
        budget['active_work_count'] = len(active)
        budget['active_work_scan_complete'] = len(active) < 1000
    return {'production_writes':False, 'provider_calls':0, 'task_count':len(rows), 'tasks':result, 'budget':budget, 'reported_episode':inspect_reported_episode(get)}


def inspect_budget(prefs, owner, seed):
    # Same account-bound format as api.model_credentials; key exists only in
    # process memory and is sent only to this account's configured provider.
    import base64, hashlib, hmac
    from datetime import datetime, timedelta, timezone
    from urllib.parse import urlsplit
    from cryptography.fernet import Fernet
    if prefs.get('llm_provider') != 'custom' or urlsplit(prefs.get('llm_base_url','')).hostname != 'api.aipaibox.com':
        return {'status':'blocked','reason':'unsupported_billing_provider'}
    derived = hmac.new(seed.encode(), f'xyz-model-key-v1:{owner}:llm_api_key'.encode(), hashlib.sha256).digest()
    token = Fernet(base64.urlsafe_b64encode(derived)).decrypt(prefs['llm_api_key_encrypted'].encode()).decode()
    request = Request('https://api.aipaibox.com/api/log/token', headers={'Authorization':'Bearer '+token})
    with urlopen(request,timeout=30) as response: data = json.load(response)['data']
    zone = timezone(timedelta(hours=8));day = datetime.now(zone).date()
    if not isinstance(data,list) or not data or min(datetime.fromtimestamp(row['created_at'],zone).date() for row in data) >= day:
        return {'status':'blocked','reason':'billing_history_does_not_span_day_boundary'}
    used = sum(row['quota'] for row in data if row['type']==2 and datetime.fromtimestamp(row['created_at'],zone).date()==day)/500000
    return {'status':'checked','beijing_date':str(day),'settled_usd':used,'remaining_usd':max(0,100-used),'daily_limit_usd':100,'scope':'configured_test_account_provider_token','model_calls':0}


def main():
    from scripts.diagnose_deployment import oci_json
    containers = oci_json(['container-instances','container-instance','get', '--container-instance-id',
        os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"') or []
    for container in containers:
        bindings = oci_json(['container-instances','container','get','--container-id',container], 'data."environment-variables"') or {}
        if bindings.get('SUPABASE_URL') and bindings.get('SUPABASE_SERVICE_KEY'):
            print(json.dumps({'failed_reading_diagnostic':inspect(bindings['SUPABASE_URL'],bindings['SUPABASE_SERVICE_KEY'],bindings.get('MODEL_CREDENTIAL_KEY') or bindings['SUPABASE_SERVICE_KEY'])}))
            return 0
    print(json.dumps({'failed_reading_diagnostic':{'blocked':'existing_database_binding_unavailable'}}))
    return 1

if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'failed_reading_diagnostic':{'blocked':True,'error_type':type(error).__name__,
            'http_status':getattr(error,'code',None) if isinstance(getattr(error,'code',None),int) else None}}))
        raise SystemExit(1)
