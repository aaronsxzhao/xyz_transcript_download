import base64
import json
from types import SimpleNamespace as NS

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scripts.run_production_sample_review import encrypt_report, safe_failure


def test_only_the_local_private_key_can_open_review_contents():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    report={'result':'Private generated notes', 'production_writes':False}
    envelope=encrypt_report(report,public)
    assert 'Private generated notes' not in json.dumps(envelope)
    aes=key.decrypt(base64.b64decode(envelope['wrapped_key']),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    plaintext=AESGCM(aes).decrypt(base64.b64decode(envelope['nonce']),base64.b64decode(envelope['ciphertext']),b'xyz-private-summary-review-v1')
    assert json.loads(plaintext)==report
    with pytest.raises(InvalidTag):
        AESGCM(aes).decrypt(base64.b64decode(envelope['nonce']),base64.b64decode(envelope['ciphertext']),b'changed-label')


def test_provider_diagnostics_never_include_error_bodies_or_credentials():
    error=RuntimeError('private-key and provider HTML')
    error.status_code=502
    error.response=httpx.Response(502,headers={'cf-ray':'reference-IAD','content-type':'text/html'},text='private-key')
    assert safe_failure(error)=={'error_type':'RuntimeError','http_status':502,'html_response':True,'reference':'reference-IAD'}
    error.response.headers['cf-ray']='https://unsafe/?key=private-key'
    assert 'reference' not in safe_failure(error)


def test_workflow_uploads_only_ciphertext_and_never_runs_with_pr_secrets():
    from pathlib import Path
    import yaml
    workflow=yaml.safe_load(Path('.github/workflows/review-saved-summary-samples.yml').read_text())
    events=workflow.get('on',workflow.get(True))
    assert 'pull_request' not in events and 'pull_request_target' not in events
    assert workflow['permissions']=={'contents':'read'}
    upload=workflow['jobs']['review']['steps'][-1]['with']
    assert upload['path']=='/tmp/xyz-review-artifacts/review.enc.json'
    assert upload['retention-days']==3
