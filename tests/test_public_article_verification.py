import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import yaml

from scripts.verify_public_article import submit


def test_example_submission_keeps_the_token_on_stdin_and_never_supplies_a_model(monkeypatch):
    run=Mock(return_value=NS(returncode=0,stdout='{"task_id":"example"}\n200'))
    monkeypatch.setattr('scripts.verify_public_article.subprocess.run',run)
    assert submit('synthetic-private-token')=='example'
    command=run.call_args.args[0]
    assert 'synthetic-private-token' not in ' '.join(command)
    assert run.call_args.kwargs['input']=='Authorization: Bearer synthetic-private-token\n'
    assert 'platform=web' in command and 'style=original' in command
    assert not any('llm_model' in part for part in command)


def test_verification_has_no_pr_secret_trigger_and_waits_for_successful_deployment():
    workflow=yaml.safe_load(Path('.github/workflows/verify-public-article.yml').read_text())
    events=workflow.get('on',workflow.get(True))
    assert set(events)=={'workflow_dispatch','workflow_run'}
    assert workflow['permissions']=={'contents':'read'}
    assert events['workflow_run']['workflows']==['Deploy to Oracle Cloud']
    assert 'success' in workflow['jobs']['verify']['if']
