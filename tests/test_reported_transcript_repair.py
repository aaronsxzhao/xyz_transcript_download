import json
from types import SimpleNamespace
from scripts.repair_reported_transcript import request_json, RepairRequestError
import pytest


def test_repair_client_keeps_owner_token_out_of_process_arguments(monkeypatch):
    calls=[]
    def run(command,**kwargs):
        calls.append((command,kwargs))
        return SimpleNamespace(returncode=0,stdout=json.dumps({'job_id':'synthetic'})+'\n200')
    monkeypatch.setattr('scripts.repair_reported_transcript.subprocess.run',run)
    assert request_json('/api/episodes/example/resummarize','private-owner-token',{})=={'job_id':'synthetic'}
    command,kwargs=calls[0]
    assert 'private-owner-token' not in str(command)
    assert kwargs['input']=='Authorization: Bearer private-owner-token\nContent-Type: application/json\n'
    assert '--insecure' not in command


def test_repair_reports_status_without_response_content(monkeypatch):
    monkeypatch.setattr('scripts.repair_reported_transcript.subprocess.run',lambda *a,**k:SimpleNamespace(returncode=0,stdout='private body\n403'))
    with pytest.raises(RepairRequestError) as error:
        request_json('/api/jobs','token')
    assert error.value.http_status==403
    assert 'private body' not in str(error.value)
