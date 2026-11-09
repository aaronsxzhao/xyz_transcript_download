"""Retired commands fail before touching credentials, databases or the network."""
import importlib
from pathlib import Path
import subprocess
import sys
import pytest

NAMES = ['repair_reported_transcript', 'repair_reported_summary',
         'repair_reported_video_summary', 'inspect_reported_video_reader',
         'verify_public_article']

@pytest.mark.parametrize('name', NAMES)
def test_retired_command_has_no_deployment_trigger_and_fails_closed(name, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Retired command attempted external work')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr('socket.socket', forbidden)
    module = importlib.import_module('scripts.' + name)
    with pytest.raises(SystemExit, match='no work was submitted'):
        module.main()
    assert not (Path('.github/workflows') / (name.replace('_', '-') + '.yml')).exists()

@pytest.mark.parametrize('name', NAMES)
def test_direct_execution_is_nonzero_and_has_no_secret_output(name):
    result = subprocess.run([sys.executable, 'scripts/' + name + '.py'], capture_output=True, text=True)
    assert result.returncode != 0
    assert result.stdout == ''
    assert result.stderr.strip() == 'Retired: use normal authenticated website actions; no work was submitted.'
