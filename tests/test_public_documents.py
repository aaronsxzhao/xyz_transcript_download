import io
import json
import time
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

import content_sources as sources
import public_content_fetch as fetch
from social_content import SocialSourceError


def page(body, head=''):
    return f'<html><head><title>Source title</title>{head}</head><body><nav>Not article navigation</nav><article><h1>Source title</h1>{body}</article></body></html>'.encode()


def test_full_article_keeps_source_structure_metadata_and_media_separate():
    body = '<h2>Original argument</h2><p>Every condition remains. <a href="/evidence">Evidence</a>.</p>' \
           '<figure><img src="/placeholder.gif" data-src="/chart.png" alt="Original chart"><figcaption>Source caption</figcaption></figure>' \
           '<table><tr><th>Value</th><th>Unit</th></tr><tr><td>100</td><td>bp</td></tr></table>' \
           '<p>Final substantive reflection.</p><iframe title="Source demonstration" src="https://www.youtube.com/embed/abcdefghijk"></iframe>'
    head = '<meta name="author" content="Author"><meta property="article:published_time" content="2024-01-01">'
    result=sources.extract_public_article(page(body,head),'https://blog.example/lesson?utm_source=copy&part=2')
    assert result.platform=='web' and result.content_type=='article' and result.media==[]
    assert result.author=='Author' and result.published.startswith('2024-01-01')
    assert result.url=='https://blog.example/lesson?part=2'
    assert result.markdown().count('# Source title')==1
    for value in ['## Original argument','Every condition remains.','https://blog.example/evidence','https://blog.example/chart.png','Source caption','| 100 | bp |','Final substantive reflection.']:
        assert value in result.body
    assert 'placeholder.gif' not in result.body and 'Not article navigation' not in result.body
    assert result.metadata()['attachments'][0]['title']=='Source demonstration'


def test_no_fixed_paragraph_or_word_cap_and_plain_text_does_not_call_a_model():
    paragraphs=[f'<p>Distinct source fact {i}: '+('original detail '*30)+'</p>' for i in range(500)]
    document=sources.extract_public_article(page(''.join(paragraphs)),'https://example.com/full')
    assert all(f'Distinct source fact {i}:' in document.body for i in range(500))
    assert sources.extract_public_article(b'Original English text.','https://example.com/note.txt','text/plain').body=='Original English text.'


@pytest.mark.parametrize('raw', [page('<p>Preview.</p>', '<script type="application/ld+json">'+json.dumps({'@type':'BlogPosting','isAccessibleForFree':False})+'</script>'),page('<p>Preview.</p><div class="paywall">Purchase required</div>'),b'<html><body><div id="app"></div></body></html>'])
def test_paywall_and_empty_dynamic_shell_are_not_completed_articles(raw):
    with pytest.raises(SocialSourceError): sources.extract_public_article(raw,'https://example.com/post')


def test_direct_media_uses_media_flow_but_embedded_media_leaves_article_intact(monkeypatch):
    monkeypatch.setattr(sources,'fetch_public',lambda *a,**k:fetch.PublicResponse('https://cdn.example/recording.mp3','audio/mpeg',b'',{}))
    result=sources.resolve_content('https://example.com/audio')
    assert result.content_type=='audio' and result.media[0]['kind']=='audio'
    monkeypatch.setattr(sources,'resolve_social_content',lambda url:'platform adapter')
    assert sources.resolve_content('https://x.com/i/status/123')=='platform adapter'


@pytest.mark.parametrize('url',['http://127.0.0.1/a','https://10.0.0.1/a','https://[::1]/a','https://localhost/a','https://host.local/a','https://user:pass@example.com/a','https://example.com:8000/a','file:///etc/passwd','https://example.com/\nHeader:value'])
def test_private_and_unsafe_destinations_are_rejected_before_network(url):
    with pytest.raises(SocialSourceError): fetch.normalize_public_url(url)


def test_dns_is_pinned_while_original_host_and_tls_identity_are_preserved(monkeypatch):
    dns=Mock(side_effect=[[(2,1,6,'',('93.184.216.34',443))],[(2,1,6,'',('127.0.0.1',443))]])
    monkeypatch.setattr(fetch.socket,'getaddrinfo',dns)
    monkeypatch.setattr(fetch.requests.utils,'get_environ_proxies',lambda url:{})
    pool=Mock();manager=Mock();manager.connection_from_url.return_value=pool
    monkeypatch.setattr(fetch.urllib3,'PoolManager',lambda **kwargs:manager)
    fetch._open('https://public.example/post',time.monotonic()+10)
    assert dns.call_count==1
    assert manager.connection_from_url.call_args.args==('https://93.184.216.34:443/post',)
    assert manager.connection_from_url.call_args.kwargs['pool_kwargs']=={'assert_hostname':'public.example','server_hostname':'public.example'}
    assert pool.urlopen.call_args.args==('GET','/post')
    assert pool.urlopen.call_args.kwargs['headers']['Host']=='public.example'
    assert 'Authorization' not in pool.urlopen.call_args.kwargs['headers']


def test_mixed_public_and_private_dns_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(fetch.socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('1.1.1.1',443)),(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(SocialSourceError): fetch.public_address('rebind.example',443)


def test_redirects_and_decoded_response_size_are_bounded(monkeypatch):
    response=Mock(status=302,headers={'Location':'http://169.254.169.254/metadata'})
    opened=Mock(return_value=(response,Mock()));monkeypatch.setattr(fetch,'_open',opened)
    with pytest.raises(SocialSourceError): fetch.fetch_public('https://public.example/post')
    assert opened.call_count==1 and response.close.called
    response=Mock(status=200,headers={'Content-Type':'text/html'});response.stream.return_value=[b'1234',b'5678']
    monkeypatch.setattr(fetch,'_open',lambda *a:(response,Mock()))
    with pytest.raises(SocialSourceError,match='too large'): fetch.fetch_public('https://public.example/post',max_bytes=5)
    response.stream.assert_called_with(65536,decode_content=True)


def test_direct_media_probe_does_not_download_the_recording(monkeypatch):
    response=Mock(status=200,headers={'Content-Type':'video/mp4'})
    monkeypatch.setattr(fetch,'_open',lambda *a:(response,Mock()))
    result=fetch.fetch_public('https://public.example/movie.mp4',media_headers_only=True)
    assert result.content_type=='video/mp4' and not response.stream.called


def test_streamed_download_cancellation_closes_connection_before_writing_more(monkeypatch):
    from api.routers.video_notes import VideoCancelledException
    response=Mock(status=200,headers={'Content-Type':'video/mp4','Content-Length':'8'})
    response.stream.return_value=iter([b'1234',b'5678'])
    manager=Mock()
    monkeypatch.setattr(fetch,'_open',lambda *a:(response,manager))
    sink=io.BytesIO()
    progress=Mock(side_effect=VideoCancelledException('Cancelled'))
    with pytest.raises(VideoCancelledException):
        fetch.fetch_public('https://public.example/movie.mp4',sink=sink,progress_callback=progress)
    progress.assert_called_once_with(4,8)
    assert sink.getvalue()==b''
    response.close.assert_called_once()
    manager.clear.assert_called_once()


def test_p_style_blog_url_can_fall_back_without_bypassing_a_real_paywall(monkeypatch):
    monkeypatch.setattr(sources,'resolve_social_content',Mock(side_effect=SocialSourceError('HTTP 404')))
    monkeypatch.setattr(sources,'fetch_public',lambda *a,**k:fetch.PublicResponse('https://blog.example/p/lesson','text/html',page('<p>Complete public blog article.</p>'),{}))
    assert sources.resolve_content('https://blog.example/p/lesson').platform=='web'
    monkeypatch.setattr(sources,'resolve_social_content',Mock(side_effect=SocialSourceError('Subscription required')))
    with pytest.raises(SocialSourceError,match='Subscription'): sources.resolve_content('https://blog.example/p/lesson')


def test_article_processing_never_resolves_a_model_and_keeps_a_saved_original_version(monkeypatch,tmp_path):
    from video_task_db import VideoTaskDB
    from api.routers import video_notes as routes
    db=VideoTaskDB(tmp_path/'web.db')
    ident=db.create_task({'url':'https://blog.example/article','platform':'web','user_id':'owner'})
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr(routes,'_broadcast_from_thread',Mock());monkeypatch.setattr(routes,'start_task',Mock())
    document=sources.extract_public_article(page('<p>First original detail.</p><p>Last original qualification.</p>'),'https://blog.example/article')
    monkeypatch.setattr(sources,'resolve_content',lambda url:document)
    resolve=Mock(side_effect=AssertionError('Original articles must not resolve a model'))
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings',resolve)
    routes.process_video_note_sync(ident,document.url,'web','detailed',['summary','screenshot'],'medium','','',False,4,3,3,'owner')
    task=db.get_task(ident,'owner',include_transcript=False)
    assert task['status']=='success' and task['style']=='original'
    assert task['source_metadata']['type']=='article' and task['source_metadata']['access']=='complete'
    assert 'First original detail.' in task['markdown'] and 'Last original qualification.' in task['markdown']
    assert len(db.get_versions(ident))==1 and not task['transcript']
    resolve.assert_not_called()


@pytest.mark.parametrize('url',['https://www.youtube.com/embed/abcdefghijk','https://www.youtube-nocookie.com/embed/abcdefghijk','https://www.youtube.com/live/abcdefghijk'])
def test_embedded_youtube_media_reuses_the_existing_watch_url_identity(url):
    from video_downloader import detect_platform,normalize_video_url
    assert detect_platform(url)=='youtube'
    assert normalize_video_url(url)=='https://www.youtube.com/watch?v=abcdefghijk'


def test_domain_fallback_is_labelled_source_not_an_invented_author():
    document=sources.extract_public_article(page('<p>Original article.</p>'),'https://blog.example/article')
    assert 'Source: blog.example' in document.markdown()
    assert 'Author: blog.example' not in document.markdown()
    attributed=sources.ContentDocument('web','https://blog.example/article','Title','Original text','Actual Author')
    assert 'Author: Actual Author' in attributed.markdown()


def test_legacy_source_attribution_is_repaired_only_in_the_generated_wrapper():
    from article_markdown import readable_article_task,repair_web_attribution
    raw='# Title\n\nAuthor: blog.example\n\n[Original source](https://blog.example/article)\n\nThe author wrote: Author: blog.example.'
    task={'platform':'web','style':'original','url':'https://blog.example/article','markdown':raw}
    result=readable_article_task(task)
    assert result['markdown'].startswith('# Title\n\nSource: blog.example')
    assert result['markdown'].endswith('The author wrote: Author: blog.example.')
    assert task['markdown']==raw
    assert repair_web_attribution('# Title\n\nAuthor: Actual Author\n\n[Original source](https://blog.example/article)','https://blog.example/article').startswith('# Title\n\nAuthor: Actual Author')
