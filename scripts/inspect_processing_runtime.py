"""Read only resource allocations needed to plan an isolated worker rollout."""
import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_deployment import oci_json, safe_log_summary

instance=oci_json(['container-instances','container-instance','get','--container-instance-id',os.environ['CONTAINER_INSTANCE_ID']], 'data')
if not instance: raise SystemExit(1)
fleet=oci_json(['container-instances','container-instance','list','--compartment-id',instance['compartment-id'],'--all'],'data.items') or []
print(json.dumps({'processing_runtime_inventory':True,
    'current_shape':instance.get('shape'),'current_allocation':instance.get('shape-config'),
    'volumes':[{'type':v.get('volume-type')} for v in instance.get('volumes') or []],
    'instances':[{'name':i.get('display-name'),'state':i.get('lifecycle-state'),'shape':i.get('shape'),'allocation':i.get('shape-config')} for i in fleet]}))
for item in instance.get('containers') or []:
    row=oci_json(['container-instances','container','get','--container-id',item['container-id']], 'data')
    print(json.dumps({'container_role':row.get('display-name'),'resource_config':row.get('resource-config'),
        'command':row.get('command'),'has_persistent_mounts':bool(row.get('volume-mounts'))}))

    # Do not emit raw logs: QR polling URLs can contain one-use login keys.
    for previous in (False, True):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime.log'
            args = ['oci','container-instances','container','retrieve-logs',
                    '--container-id',item['container-id'],'--file',str(path)]
            if previous: args.extend(['--is-previous','true'])
            result = subprocess.run(args,capture_output=True,timeout=60)
            report = {'previous_run':previous,'container_role':row.get('display-name')}
            if result.returncode == 0 and path.exists():
                report['logs'] = safe_log_summary(path.read_text(errors='replace'))
            else: report['logs_available'] = False
            print(json.dumps(report))

    # Read only the two explicitly authorized Nov11 disposable import records.
    # Never export bindings, domain content or raw container logs.
    bindings = row.get('environment-variables') or {}
    if bindings.get('SUPABASE_URL') and bindings.get('SUPABASE_SERVICE_KEY'):
        from scripts.inspect_pending_imports import inspect_bindings
        print(json.dumps({'pending_import_diagnostic':inspect_bindings(bindings)}))
