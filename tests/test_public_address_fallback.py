"""Public source fallback must preserve DNS pinning and the shared deadline."""
from unittest.mock import Mock

import pytest
import urllib3

import public_content_fetch as fetch
from social_content import SocialSourceError


@pytest.fixture
def connection(monkeypatch):
    dns = Mock(return_value=[(10, 1, 6, '', ('2606:4700:4700::1111', 443, 0, 0)),
                             (2, 1, 6, '', ('1.1.1.1', 443))])
    monkeypatch.setattr(fetch.socket, 'getaddrinfo', dns)
    monkeypatch.setattr(fetch.requests.utils, 'get_environ_proxies', lambda url: {})
    first, second, manager = Mock(), Mock(), Mock()
    manager.connection_from_url.side_effect = [first, second]
    monkeypatch.setattr(fetch.urllib3, 'PoolManager', lambda **kwargs: manager)
    monkeypatch.setattr(fetch.time, 'monotonic', lambda: 1)
    return dns, manager, first, second


def test_unreachable_first_address_uses_validated_alternative_without_resolving_again(connection):
    dns, manager, first, second = connection
    first.urlopen.side_effect = urllib3.exceptions.NewConnectionError(first, 'Network unreachable')
    response, returned = fetch._open('https://source.example/post?a=1', 10)
    assert returned is manager and response is second.urlopen.return_value
    assert dns.call_count == 1
    calls = manager.connection_from_url.call_args_list
    assert calls[0].args[0] == 'https://[2606:4700:4700::1111]:443/post?a=1'
    assert calls[1].args[0] == 'https://1.1.1.1:443/post?a=1'
    for call in calls:
        assert call.kwargs['pool_kwargs'] == {'assert_hostname': 'source.example', 'server_hostname': 'source.example'}
    assert second.urlopen.call_args.kwargs['headers']['Host'] == 'source.example'
    manager.clear.assert_not_called()


def test_address_fallback_stops_at_the_original_deadline(connection, monkeypatch):
    _, manager, first, second = connection
    monkeypatch.setattr(fetch.time, 'monotonic', Mock(side_effect=[1, 11]))
    first.urlopen.side_effect = urllib3.exceptions.ConnectTimeoutError('Connection timed out')
    with pytest.raises(TimeoutError):
        fetch._open('https://source.example/post', 10)
    second.urlopen.assert_not_called()
    manager.clear.assert_called_once()


@pytest.mark.parametrize('error', [urllib3.exceptions.ReadTimeoutError(None, '/post', 'Timed out'),
                                  urllib3.exceptions.SSLError('Certificate mismatch')])
def test_read_and_certificate_failures_are_not_retried_on_other_addresses(connection, error):
    _, manager, first, second = connection
    first.urlopen.side_effect = error
    with pytest.raises(type(error)):
        fetch._open('https://source.example/post', 10)
    second.urlopen.assert_not_called()
    manager.clear.assert_called_once()


def test_any_private_dns_answer_blocks_all_attempts(connection):
    dns, manager, first, second = connection
    dns.return_value.append((2, 1, 6, '', ('127.0.0.1', 443)))
    with pytest.raises(SocialSourceError):
        fetch._open('https://source.example/post', 10)
    manager.connection_from_url.assert_not_called()
