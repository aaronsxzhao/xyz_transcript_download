"""A healthy old process must never count as a successful deployment."""
import io
import json
from unittest.mock import patch
from urllib.error import URLError

import pytest

from scripts.verify_deployment import verify_deployment


@pytest.mark.parametrize("payload,expected", [
    ({"status": "ok", "revision": "new"}, True),
    ({"status": "ok", "revision": "old"}, False),
    ({"status": "failed", "revision": "new"}, False),
    ({"status": "ok"}, False),
])
def test_deployment_requires_healthy_expected_revision(payload, expected):
    with patch("scripts.verify_deployment.urllib.request.urlopen", side_effect=lambda *a, **kw: io.BytesIO(json.dumps(payload).encode())):
        assert verify_deployment("new", attempts=2, interval=0) is expected


def test_deployment_fails_when_api_is_unreachable():
    with patch("scripts.verify_deployment.urllib.request.urlopen", side_effect=URLError("synthetic outage")):
        assert verify_deployment("new", attempts=2, interval=0) is False


def test_deployment_waits_for_new_revision():
    responses = [io.BytesIO(b'{"status":"ok","revision":"old"}'), io.BytesIO(b'{"status":"ok","revision":"new"}')]
    with patch("scripts.verify_deployment.urllib.request.urlopen", side_effect=responses):
        assert verify_deployment("new", attempts=2, interval=0) is True
