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

def safe_report(report):
    report = report if isinstance(report, dict) else {}
    safe = {}
    for key in ('delivery', 'coverage_ledger', 'verification'):
        source = report.get(key) or {}
        if not isinstance(source, dict): continue
        row = {k:source[k] for k in COUNTERS if type(source.get(k)) in (int, float, bool)
               and math.isfinite(source[k])}
        if source.get('status') in ('blocked','accepted','acceptable','unverified','model_reviewed','failed'):
            row['status'] = source['status']
        if source.get('reason') in ('coverage','grounding','review','ValueError','SummaryOutputError','ReadingProviderError'):
            row['reason'] = source['reason']
        if key == 'coverage_ledger':
            row['inventory_error_types'] = {name:sum(isinstance(e,dict) and e.get('error_type')==name for e in source.get('inventory_failures',[]) or []) for name in ('ValueError','SummaryOutputError','APIConnectionError','APITimeoutError','TimeoutError','APIStatusError','RateLimitError','RuntimeError','ReadTimeout','ConnectError','ConnectionError','ModelRequestTimeout','InternalServerError','BadRequestError','AuthenticationError','PermissionDeniedError','NotFoundError','UnprocessableEntityError')}
            row['inventory_failures_recorded'] = len(source.get('inventory_failures',[]) or [])
            row['inventory_failures_available'] = 'inventory_failures' in source
            row['item_status_counts'] = {state:sum(isinstance(i,dict) and i.get('status')==state for i in source.get('items',[]) or [])
                for state in ('covered','missing','partial','contradicted','unverified','context_only')}
        safe[key] = row
    return safe


def inspect(base, key):
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
    return {'production_writes':False, 'provider_calls':0, 'task_count':len(rows), 'tasks':result}


def main():
    from scripts.diagnose_deployment import oci_json
    containers = oci_json(['container-instances','container-instance','get', '--container-instance-id',
        os.environ['CONTAINER_INSTANCE_ID']], 'data.containers[*]."container-id"') or []
    for container in containers:
        bindings = oci_json(['container-instances','container','get','--container-id',container], 'data."environment-variables"') or {}
        if bindings.get('SUPABASE_URL') and bindings.get('SUPABASE_SERVICE_KEY'):
            print(json.dumps({'failed_reading_diagnostic':inspect(bindings['SUPABASE_URL'],bindings['SUPABASE_SERVICE_KEY'])}))
            return 0
    print(json.dumps({'failed_reading_diagnostic':{'blocked':'existing_database_binding_unavailable'}}))
    return 1

if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'failed_reading_diagnostic':{'blocked':True,'error_type':type(error).__name__,
            'http_status':getattr(error,'code',None) if isinstance(getattr(error,'code',None),int) else None}}))
        raise SystemExit(1)
