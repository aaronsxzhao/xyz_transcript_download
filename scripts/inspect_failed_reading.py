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
    'inventory_transport_retries', 'inventory_split_retries', 'inventory_recovered_batches', 'inventory_batches', 'reviewed', 'review_attempts', 'review_parts', 'final_coverage_attempts',
    'initial_grounding_concerns','stale_gap_receipts_refreshed','empty_repair_rechecks_avoided','regression_pruning_attempts',
    'reused_covered_receipts','existing_redundancy_flags','changed_support_regressions',
    'contradiction_obligations_validated','contradiction_source_corrections')

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
                    'rejected_paragraphs','source_corrected_items','logical_requests_reported','coverage_ratio',
                    'stale_gap_receipts_refreshed','empty_repair_rechecks_avoided','regression_pruning_attempts',
                    'reused_covered_receipts','existing_redundancy_flags','changed_support_regressions',
                    'contradiction_obligations_validated','contradiction_source_corrections'):
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
    if type(report.get('final_source_capacity_fallback')) is bool:
        safe['final_source_capacity_fallback']=report['final_source_capacity_fallback']
    if type(report.get('final_source_review_parts')) is int and 0<=report['final_source_review_parts']<=100000:
        safe['final_source_review_parts']=report['final_source_review_parts']
    if report.get('source_layout') in ('original-lines','lossless-timed-groups-v1'):
        safe['source_layout']=report['source_layout']
    if type(report.get('source_units')) is int and 0<report['source_units']<=100000:
        safe['source_units']=report['source_units']
    if type(report.get('inventory_guided_draft')) is bool:safe['inventory_guided_draft']=report['inventory_guided_draft']
    if type(report.get('inventory_source_items')) is int and 0<=report['inventory_source_items']<=100000:
        safe['inventory_source_items']=report['inventory_source_items']
    if isinstance(report.get('grounding_repair_sizes'),list):
        safe['grounding_repair_sizes']=[{k:v for k,v in row.items()
            if k in ('paragraphs','characters_before','characters_after','covered_obligations_supplied','source_obligations_supplied',
                     'original_rejections_used','rejected_prose_characters')
            and type(v) is int and 0<=v<=1000000}
            for row in report['grounding_repair_sizes'][:3] if isinstance(row,dict)]
    if isinstance(report.get('grounding_preservation_checks'),list):
        safe['grounding_preservation_checks']=[{k:v for k,v in row.items()
            if k in ('obligations','source_supported','missing_supported') and type(v) is int and 0<=v<=100000}
            for row in report['grounding_preservation_checks'][:50] if isinstance(row,dict)]
    if type(report.get('late_contradiction_repair_attempts')) is int and 0 <= report['late_contradiction_repair_attempts'] <= 1:
        safe['late_contradiction_repair_attempts'] = report['late_contradiction_repair_attempts']
    if report.get('late_contradiction_repair_origin') in ('following_review_repair','same_delivery_iteration','final_source_review'):
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
            allowed=('incomplete_matches','unknown_paragraph','missing_support','missing_judgement',
                'invalid_status','incomplete_proposal_check','raw_support','source_obligations_unverified',
                'schema_or_provider_failure','invalid_match','invalid_support','invalid_missing_meaning',
                'output_invalid','output_empty','output_length','output_capacity','output_content_filter')
            row['check_failure_counts']={label:count for label,count in (source.get('check_failure_counts') or {}).items()
                if label in allowed and type(count) is int and 0<=count<=10000}
            names=('ValueError','TypeError','KeyError','SummaryOutputError','APIConnectionError','APITimeoutError',
                'TimeoutError','APIStatusError','RateLimitError','RuntimeError','ReadTimeout','InternalServerError','OtherError')
            row['check_failure_types']={name:count for name,count in (source.get('check_failure_types') or {}).items()
                if name in names and type(count) is int and 0<=count<=10000}
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
        *('model.phase.'+phase for phase in ('draft','grounding','inventory','match','repair','validate_inventory','repair_grounding','verify_grounding_preservation','other'))}
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


def summarize_token_error_metadata(rows, day, zone):
    """Only count recognized structured error labels; never export messages.

    Missing provider error logs are not proof that HTTP requests succeeded.
    These are token-wide day aggregates, not per-run causal attribution.
    """
    from datetime import datetime
    codes = {'context_length_exceeded','invalid_request_error','invalid_value',
        'unsupported_parameter','unsupported_value','rate_limit_exceeded',
        'insufficient_quota','model_not_found','string_above_max_length','content_filter',
        'invalid_api_key','max_tokens_exceeded'}
    params = {'temperature','max_completion_tokens','max_tokens','response_format',
        'messages','model','reasoning_effort','service_tier'}
    statuses = {400,401,403,404,408,409,413,422,429,500,502,503,504}
    result = {'error_records_today':0,'recognized_code_counts':{},
              'recognized_param_counts':{},'http_status_counts':{},'unclassified_records':0}
    for row in rows:
        if not isinstance(row,dict) or row.get('type') != 5:
            continue
        timestamp = row.get('created_at')
        if type(timestamp) not in (int,float) or not math.isfinite(timestamp):
            continue
        if datetime.fromtimestamp(timestamp,zone).date() != day:
            continue
        result['error_records_today'] += 1
        objects = [row]
        for key in ('other','content'):
            value = row.get(key)
            if isinstance(value,str) and len(value)<=65536:
                try: value=json.loads(value)
                except ValueError: value=None
            if isinstance(value,dict): objects.append(value)
        found_codes=set();found_params=set();found_statuses=set()
        for obj in objects:
            for item in (obj,obj.get('error'),obj.get('provider_error')):
                if not isinstance(item,dict): continue
                for key in ('code','type'):
                    value=item.get(key)
                    if isinstance(value,str) and value in codes: found_codes.add(value)
                value=item.get('param')
                if isinstance(value,str) and value in params: found_params.add(value)
                for key in ('http_status','status_code'):
                    value=item.get(key)
                    if type(value) is int and value in statuses: found_statuses.add(str(value))
        for key, values in (('recognized_code_counts',found_codes),
                            ('recognized_param_counts',found_params),('http_status_counts',found_statuses)):
            for value in values: result[key][value]=result[key].get(value,0)+1
        if not found_codes and not found_params and not found_statuses:
            result['unclassified_records'] += 1
    return result


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
    return {'status':'checked','beijing_date':str(day),'settled_usd':used,'remaining_usd':max(0,100-used),'daily_limit_usd':100,'scope':'configured_test_account_provider_token','model_calls':0,
            'provider_error_metadata':summarize_token_error_metadata(data,day,zone)}


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
