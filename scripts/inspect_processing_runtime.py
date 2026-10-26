"""Read only resource allocations needed to plan an isolated worker rollout."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.diagnose_deployment import oci_json

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
