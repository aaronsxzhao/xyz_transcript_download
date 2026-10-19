"""A healthy old process must never count as a successful deployment."""
import json
from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.verify_deployment import verify_deployment


def response(payload, code=200, exit_code=0):
    return SimpleNamespace(stdout=json.dumps(payload) + f"\n{code}", returncode=exit_code)


@pytest.mark.parametrize("payload,expected", [
    ({"status": "ok", "revision": "new"}, True),
    ({"status": "ok", "revision": "old"}, False),
    ({"status": "failed", "revision": "new"}, False),
    ({"status": "ok"}, False),
])
def test_deployment_requires_healthy_expected_revision(payload, expected):
    with patch("scripts.verify_deployment.subprocess.run", return_value=response(payload)) as request:
        assert verify_deployment("new", attempts=2, interval=0) is expected
        assert request.call_args.args[0][0] == "curl"
        assert "--insecure" not in request.call_args.args[0]


def test_deployment_fails_when_api_is_unreachable():
    with patch("scripts.verify_deployment.subprocess.run", side_effect=TimeoutExpired("curl", 15)):
        assert verify_deployment("new", attempts=2, interval=0) is False


def test_deployment_waits_for_new_revision():
    responses = [response({"status": "ok", "revision": "old"}), response({"status": "ok", "revision": "new"})]
    with patch("scripts.verify_deployment.subprocess.run", side_effect=responses):
        assert verify_deployment("new", attempts=2, interval=0) is True


def test_deployment_reports_http_failure(capsys):
    with patch("scripts.verify_deployment.subprocess.run", return_value=response({}, 403, 22)):
        assert verify_deployment("new", attempts=1, interval=0) is False
    assert "HTTP 403" in capsys.readouterr().out
