import json
import time
from unittest.mock import Mock, AsyncMock

import pytest

import social_content as social


@pytest.mark.parametrize('url,expected', [
    ('https://twitter.com/person/status/123456?utm_source=x','https://x.com/i/status/123456'),
    ('https://x.com/i/status/123456','https://x.com/i/status/123456'),
    ('https://mobile.x.com/person/status/123456','https://x.com/i/status/123456'),
    ('https://twitter.com/statuses/123456','https://x.com/i/status/123456'),
    ('https://x.com/i/web/status/123456/video/1','https://x.com/i/status/123456'),
    ('https://x.com/i/article/123456','https://x.com/i/article/123456'),
    ('https://writer.substack.com/p/lesson?utm_source=x','https://writer.substack.com/p/lesson'),
    ('https://writing.example/p/lesson','https://writing.example/p/lesson'),
])
def test_share_urls_normalize_without_network_calls(url,expected):
    assert social.normalize_social_url(url)==expected
    from video_downloader import normalize_video_url,detect_platform
    assert normalize_video_url(url)==expected
    assert detect_platform(url) in ('twitter','substack')


@pytest.mark.parametrize('url', ['https://x.com/person','javascript:alert(1)','https://x.com.evil.example/person/status/123','https://user:pass@x.com/person/status/123','https://x.com:999/status/123'])
def test_profile_spoof_and_unsafe_urls_are_not_treated_as_posts(url):
    with pytest.raises(social.SocialSourceError): social.normalize_social_url(url)


def test_long_tweet_images_and_quoted_context_are_preserved_without_summarization(monkeypatch):
    text='Original English details. 原文细节。\n' * 2000
    monkeypatch.setattr(social,'_json',lambda *a:{'code':200,'status':{'id':'123','text':text,'author':{'name':'Writer'},'created_at':'2026-10-24T12:00:00Z',
        'media':{'photos':[{'url':'https://pbs.twimg.com/photo.jpg','altText':'Original chart'}]},'quote':{'text':'Quoted condition','url':'https://x.com/i/status/99'}}})
    source=social.resolve_social_content('https://x.com/writer/status/123')
    assert text.strip() in source.body
    assert source.media==[]
    assert 'Original chart' in source.body and 'Quoted condition' in source.body
    assert 'Writer' in source.markdown() and '2026-10-24' in source.markdown()


def test_article_body_not_preview_and_original_headings_are_used(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'code':200,'status':{'text':'Introduction','article':{'title':'Research','preview_text':'Do not use just this preview','content':{'blocks':[
        {'type':'header-one','text':'Original heading'},{'type':'unstyled','text':'Complete details and conditions.'}]}},'media':{}}})
    source=social.resolve_social_content('https://x.com/i/status/123')
    assert '## Original heading' in source.body
    assert 'Complete details and conditions.' in source.body
    assert 'Do not use just this preview' not in source.body


def test_an_article_preview_is_not_saved_as_a_complete_article(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'code':200,'status':{'text':'Teaser','article':{'title':'Research','preview_text':'Preview only'}}})
    with pytest.raises(social.SocialSourceError,match='preview'):social.resolve_social_content('https://x.com/i/status/123')


def test_all_video_attachments_retain_source_order(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'code':200,'status':{'text':'Both clips matter','media':{'videos':[
        {'url':'https://video.twimg.com/first.mp4','duration':12},{'url':'https://video.twimg.com/second.mp4','duration':24}]}}})
    source=social.resolve_social_content('https://x.com/i/status/123')
    assert [item['url'] for item in source.media]==['https://video.twimg.com/first.mp4','https://video.twimg.com/second.mp4']


@pytest.mark.parametrize('audience',['paid','only_paid','founding'])
def test_paid_substack_previews_never_become_successful_full_text(monkeypatch,audience):
    monkeypatch.setattr(social,'_json',lambda *a:{'title':'Paid article','audience':audience,'body_html':'<p>Only a preview</p>'})
    with pytest.raises(social.SocialSourceError,match='subscription'):social.resolve_social_content('https://writer.substack.com/p/paid')


def test_substack_structure_links_images_and_complete_body_are_retained(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'title':'Full original','audience':'everyone','body_html':'<h2>Original heading</h2><p>First <strong>important</strong> detail.</p><p>Final condition.</p><img src="/chart.png" alt="Evidence"><a href="/source">Source</a><table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>',
        'publishedBylines':[{'name':'Author'}],'post_date':'2026-10-24T12:00:00Z'})
    source=social.resolve_social_content('https://writer.substack.com/p/full')
    assert '## Original heading' in source.body and '**important**' in source.body and 'Final condition.' in source.body
    assert 'https://writer.substack.com/chart.png' in source.body
    assert '| A | B |' in source.body and '| 1 | 2 |' in source.body


def test_substack_notes_keep_paragraphs_original_language_and_marks(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'comment':{'body_json':{'type':'doc','content':[
        {'type':'paragraph','content':[{'type':'text','text':'English original','marks':[{'type':'bold'}]}]},
        {'type':'paragraph','content':[{'type':'text','text':'Second condition'}]}]},'user':{'name':'Author'}}})
    source=social.resolve_social_content('https://substack.com/@writer/note/c-123')
    assert '**English original**\n\nSecond condition' in source.body


def test_current_substack_reader_note_response_and_attachment_shape(monkeypatch):
    read=Mock(return_value={'item':{'comment':{'body':'Complete original Note','attachments':[{'type':'image','imageUrl':'https://substackcdn.com/chart.png'}]},'user':{'name':'Writer'}}})
    monkeypatch.setattr(social,'_json',read)
    source=social.resolve_social_content('https://substack.com/@writer/note/c-123')
    assert read.call_args.args[0]=='https://substack.com/api/v1/reader/comment/123'
    assert source.author=='Writer' and 'Complete original Note' in source.body and 'chart.png' in source.body


def test_substack_app_links_retain_identifiers_needed_for_redirect_resolution():
    url=social.normalize_social_url('https://substack.com/app-link/post?publication_id=12&post_id=34&utm_source=email')
    assert 'post_id=34' in url and 'publication_id=12' in url and 'utm_source' not in url


def test_substack_podcast_routes_to_media_instead_of_summarizing_show_notes(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'title':'Audio episode','body_html':'<p>Original show notes</p>','podcast_url':'https://api.substack.com/audio.mp3','podcast_duration':120})
    source=social.resolve_social_content('https://writer.substack.com/p/audio')
    assert source.media[0]['kind']=='audio' and 'Original show notes' in source.body


def test_substack_video_selects_the_public_mp4_stream_explicitly(monkeypatch):
    monkeypatch.setattr(social,'_json',lambda *a:{'title':'Video episode','body_html':'<p>Original video notes</p>','videoUpload':{'id':'video-123','duration':120}})
    source=social.resolve_social_content('https://writer.substack.com/p/video')
    assert source.media==[{'url':'https://writer.substack.com/api/v1/video/upload/video-123/src?type=mp4','kind':'video','duration':120}]


def test_source_html_removes_scripts_but_keeps_literal_code_and_text():
    result=social.html_markdown('<h2>Title</h2><script>bad()</script><pre><code>a &lt; b</code></pre><a href="javascript:bad()">Label</a>','https://writer.substack.com/p/post')
    assert 'bad()' not in result and 'a < b' in result and 'Label' in result


def test_inline_source_code_is_not_rewritten_as_escaped_prose():
    result=social.html_markdown('<p>Use <code>a*b[0]</code>.</p><!-- hidden comment -->','https://writer.substack.com/p/post')
    assert 'a*b[0]' in result and 'a\\*b' not in result and 'hidden comment' not in result


def test_private_addresses_are_rejected_before_a_network_request(monkeypatch):
    monkeypatch.setattr(social.socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    request=Mock();monkeypatch.setattr(social.requests,'get',request)
    with pytest.raises(social.SocialSourceError,match='public address'):social._read('https://writer.substack.com/p/post',time.monotonic()+10)
    request.assert_not_called()


def test_redirect_destinations_are_rechecked_and_responses_closed(monkeypatch):
    monkeypatch.setattr(social.socket,'getaddrinfo',lambda host,*a,**k:[(None,None,None,None,('127.0.0.1' if host=='internal.example' else '8.8.8.8',443))])
    response=Mock(status_code=302,headers={'Location':'https://internal.example/private'})
    request=Mock(return_value=response);monkeypatch.setattr(social.requests,'get',request)
    with pytest.raises(social.SocialSourceError):social._read('https://writer.substack.com/p/post',time.monotonic()+10)
    request.assert_called_once();response.close.assert_called_once()


def test_media_redirects_cannot_target_private_addresses(monkeypatch):
    monkeypatch.setattr(social.socket,'getaddrinfo',lambda host,*a,**k:[(None,None,None,None,('127.0.0.1' if host=='internal.example' else '8.8.8.8',443))])
    response=Mock(status_code=302,headers={'Location':'https://internal.example/private'})
    request=Mock(return_value=response);monkeypatch.setattr(social.requests,'get',request)
    with pytest.raises(social.SocialSourceError):social.public_media_target('https://api.substack.com/audio.mp3')
    request.assert_called_once();response.close.assert_called_once()


def test_social_cover_domains_work_with_existing_persistent_artwork_cache():
    from api.covers import validate_url
    assert validate_url('https://pbs.twimg.com/cover.jpg')=='pbs.twimg.com'
    assert validate_url('https://substackcdn.com/image.jpg')=='substackcdn.com'
    with pytest.raises(Exception):validate_url('https://substackcdn.com.evil.example/image.jpg')


@pytest.mark.asyncio
async def test_admission_is_fast_normalized_and_does_not_fetch_sources(client,monkeypatch):
    import api.routers.video_notes as routes
    resolve=Mock(side_effect=AssertionError('Only workers read remote sources'))
    monkeypatch.setattr(social,'resolve_social_content',resolve)
    monkeypatch.setattr(routes,'enqueue_video_note',AsyncMock())
    response=await client.post('/api/video-notes/generate-json',json={'url':'https://twitter.com/writer/status/123?tracking=x'})
    assert response.status_code==200
    from video_task_db import get_video_task_db
    task=get_video_task_db().get_task(response.json()['task_id'],'local')
    assert task['platform']=='twitter' and task['url']=='https://x.com/i/status/123'
    resolve.assert_not_called()
    bad=await client.post('/api/video-notes/generate-json',json={'url':'https://x.com/writer'})
    assert bad.status_code==400


@pytest.fixture
def worker(monkeypatch,tmp_path):
    from video_task_db import VideoTaskDB
    from api.routers import video_notes as routes
    db=VideoTaskDB(tmp_path/'social.db')
    task_id=db.create_task({'id':'social-test','url':'https://x.com/i/status/123','platform':'twitter','user_id':'owner'})
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr(routes,'_broadcast_from_thread',Mock())
    monkeypatch.setattr(routes,'start_task',Mock())
    def run():routes.process_video_note_sync(task_id,'https://x.com/i/status/123','twitter','detailed',['summary'],'medium','','',False,4,3,3,'owner')
    return db,task_id,run


def test_text_import_never_reads_model_settings_and_is_saved_atomically(worker,monkeypatch):
    db,task_id,run=worker
    monkeypatch.setattr(social,'resolve_social_content',lambda url:social.SocialContent('twitter',url,'Original title','All original details.\n\nLast paragraph.','Writer'))
    resolve=Mock(side_effect=AssertionError('No model is needed for text'));monkeypatch.setattr('api.llm_settings.resolve_llm_settings',resolve)
    run()
    task=db.get_task(task_id,'owner')
    assert task['status']=='success' and task['style']=='original' and task['formats']==['original']
    assert 'Last paragraph.' in task['markdown'] and task['model']==''
    assert len(db.get_versions(task_id))==1
    resolve.assert_not_called()


def test_restricted_source_fails_with_reason_without_creating_a_summary(worker,monkeypatch):
    db,task_id,run=worker
    monkeypatch.setattr(social,'resolve_social_content',Mock(side_effect=social.SocialSourceError('Subscription required; preview not complete')))
    run();task=db.get_task(task_id,'owner')
    assert task['status']=='failed' and 'Subscription' in task['message']
    assert not task['markdown'] and not db.get_versions(task_id)


def test_media_uses_existing_summary_pipeline_and_retains_original_post(worker,monkeypatch):
    from video_downloader import VideoMetadata
    db,task_id,run=worker
    source=social.SocialContent('twitter','https://x.com/i/status/123','Video lesson','An important original caption.','Writer',thumbnail='https://pbs.twimg.com/image.jpg',
        media=[{'url':'https://video.twimg.com/clip.mp4','kind':'video','duration':120}])
    monkeypatch.setattr(social,'resolve_social_content',lambda url:source)
    downloader=Mock()
    downloader.get_metadata.return_value=VideoMetadata(title=source.title,thumbnail=source.thumbnail,channel='Writer',duration=0)
    downloader.get_subtitles.return_value=[{'text':'Complete English transcript and conditions. '*10,'start':0,'end':120}]
    monkeypatch.setattr('social_downloader.SocialDownloader',lambda src:downloader)
    monkeypatch.setattr('api.user_settings.get_user_settings',lambda owner:{})
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings',lambda *a:{'api_key':'test','base_url':'https://test.example','model':'selected-model'})
    summarizer=Mock();summarizer.generate_note.return_value='# English lesson\n\nAll meaningful conditions.'
    monkeypatch.setattr('note_summarizer.get_note_summarizer',lambda **kw:summarizer)
    run()
    task=db.get_task(task_id,'owner')
    assert task['status']=='success',task['message']
    assert 'All meaningful conditions.' in task['markdown'] and 'An important original caption.' in task['markdown']
    assert summarizer.generate_note.call_args.kwargs['transcript_text'].startswith('Complete English transcript')
    assert task['transcript']['text'].startswith('Complete English transcript')
    assert task['duration']==120
