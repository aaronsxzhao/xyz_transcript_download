import re
from unittest.mock import Mock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_connection_failure_returns_retryable_error_and_server_timing(client):
    database = Mock()
    database.get_summary.side_effect = httpx.RemoteProtocolError('private upstream information')
    with patch('api.routers.summaries.get_db', return_value=database):
        response = await client.get('/api/summaries/existing')
    assert response.status_code == 503
    assert response.headers['retry-after'] == '1'
    assert 'private upstream information' not in response.text
    assert re.fullmatch(r'app;dur=\d+\.\d', response.headers['server-timing'])
