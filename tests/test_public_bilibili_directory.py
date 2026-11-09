from unittest.mock import Mock
import pytest
from bilibili_parts import public_collection_metadata

BASE = 'https://www.bilibili.com/video/BVexample'


def response(monkeypatch, payload, status=200):
    result = Mock(status_code=status)
    result.json.return_value = payload
    context = Mock()
    context.__enter__ = Mock(return_value=result)
    context.__exit__ = Mock(return_value=False)
    get = Mock(return_value=context)
    monkeypatch.setattr('requests.get', get)
    return get


def test_public_directory_has_bounded_fixed_host_read_without_credentials(monkeypatch):
    get = response(monkeypatch, {'code': 0, 'data': [
        {'page': i, 'cid': i, 'duration': 60, 'part': f'Part {i}'} for i in (1, 2)]})
    result = public_collection_metadata(BASE+'?p=2')
    assert result['bilibili_part']['page'] == 2
    assert len(result['bilibili_parts']) == 2
    assert get.call_args.args == ('https://api.bilibili.com/x/player/pagelist',)
    options = get.call_args.kwargs
    assert options['timeout'] == 15 and options['allow_redirects'] is False
    assert 'Cookie' not in options['headers'] and 'cookies' not in options


@pytest.mark.parametrize('payload,status', [
    ({'code': -412}, 200), ({}, 429),
    ({'code': 0, 'data': {'videos': 2, 'pages': [{'page': 1, 'cid': 1, 'duration': 60}]}}, 200),
    ({'code': 0, 'data': {}}, 200),
    ({'code': 0, 'data': []}, 200),
    ({'code': 0, 'data': [{'page': 2, 'cid': 2, 'duration': 60}]}, 200),
    ({'code': 0, 'data': [None]}, 200),
])
def test_rejected_or_incomplete_directory_is_not_accepted(monkeypatch,payload,status):
    response(monkeypatch,payload,status)
    with pytest.raises(ValueError):
        public_collection_metadata(BASE)


@pytest.mark.parametrize('url', ['http://localhost/video/BVexample', 'https://www.bilibili.com@evil.test/video/BVexample', 'https://www.bilibili.com:444/video/BVexample'])
def test_untrusted_source_never_requested(monkeypatch,url):
    get = response(monkeypatch,{})
    with pytest.raises(ValueError): public_collection_metadata(url)
    get.assert_not_called()


def test_public_pages_remain_readable_when_overview_rejects_anonymous_read(monkeypatch):
    from unittest.mock import MagicMock
    def source(url, **kwargs):
        result = MagicMock()
        result.__enter__.return_value = result
        if url.endswith('/x/web-interface/view'):
            result.status_code = 412
        else:
            assert url.endswith('/x/player/pagelist')
            result.status_code = 200
            result.json.return_value = {'code':0,'data':[
                {'page':i,'cid':100+i,'duration':60,'part':f'Chapter {i}'} for i in (1,2)]}
        return result
    monkeypatch.setattr('requests.get',source)
    result = public_collection_metadata(BASE+'?p=2')
    assert [part['page'] for part in result['bilibili_parts']] == [1,2]
    assert result['bilibili_part']['cid'] == '102'
    assert result['bilibili_parts'][0]['title'].endswith('Chapter 1')


def test_pagelist_does_not_substitute_first_part_for_missing_selected_part(monkeypatch):
    response(monkeypatch, {'code':0,'data':[{'page':1,'cid':1,'duration':60}]})
    with pytest.raises(ValueError,match='Saved part is absent'):
        public_collection_metadata(BASE+'?p=2')
