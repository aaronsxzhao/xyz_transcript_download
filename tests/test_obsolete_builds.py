"""Exercise cleanup decisions without calling GitHub or touching production."""
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]


def workflow():
    return yaml.safe_load((ROOT/'.github/workflows/retire-obsolete-builds.yml').read_text())


@pytest.mark.parametrize('release', [None,'in_progress','completed'])
@pytest.mark.parametrize('newer_main', [False,True])
def test_only_old_builds_without_started_release_steps_are_cancelled(release,newer_main):
    script=workflow()['jobs']['retire-builds']['steps'][0]['with']['script']
    harness='''
const cancelled=[];
const context={repo:{owner:'owner',repo:'repo'},sha:'new',runId:100};
const core={info:()=>{}};
const github={rest:{git:{getRef:async()=>({data:{object:{sha:MAIN_SHA}}})},actions:{
 listWorkflowRuns:async()=>({data:{workflow_runs:[{id:1,head_sha:'old'},{id:2,head_sha:'new'},{id:101,head_sha:'future'}]}}),
 listJobsForWorkflowRun:async()=>({data:{jobs:[{steps:STEPS}]}}),
 cancelWorkflowRun:async({run_id})=>cancelled.push(run_id)
}}};
(async()=>{SCRIPT
 process.stdout.write(JSON.stringify(cancelled));
})().catch(e=>{process.stderr.write(String(e));process.exit(1)});
'''
    steps=[{'name':'Build and push ARM image','status':'in_progress'}]
    if release:steps.append({'name':'Restart Container Instance','status':release})
    source=harness.replace('MAIN_SHA',json.dumps('future' if newer_main else 'new')).replace('STEPS',json.dumps(steps)).replace('SCRIPT',script)
    result=subprocess.run(['node','-e',source],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)==([] if release or newer_main else [1])


def test_cleanup_does_not_cancel_deployment_workflow_globally():
    cleanup=workflow()['jobs']['retire-builds']
    assert cleanup['permissions']=={'contents':'read','actions':'write'}
    deploy=yaml.safe_load((ROOT/'.github/workflows/deploy-oracle.yml').read_text())
    assert deploy['concurrency']['cancel-in-progress'] is False
    build=next(step for step in deploy['jobs']['build-and-deploy']['steps'] if step['name']=='Build and push ARM image')
    assert build['timeout-minutes']==25
    # PyYAML's YAML 1.1 loader reads the GitHub Actions key 'on' as True.
    assert workflow()[True]['push']['paths']==deploy[True]['push']['paths']
