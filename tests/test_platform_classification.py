"""Import classification follows the actual source host, never the RSS directory."""
from unittest.mock import AsyncMock
import pytest
from apple_podcasts_client import detect_platform as podcast_platform
from video_downloader import detect_platform as video_platform,normalize_video_url


@pytest.mark.parametrize('url,expected',[
 ('https://open.spotify.com/episode/08tccyLPpPurxtPPrezQGZ','spotify'),
 ('https://podcasts.apple.com/podcast/id123','apple'),
 ('https://www.xiaoyuzhoufm.com/podcast/123','xiaoyuzhou'),
 ('https://www.youtube.com/watch?v=abcdefghijk','youtube'),
 ('https://www.bilibili.com/video/BV1234567890','bilibili'),
 ('https://v.douyin.com/abc','douyin'),('https://v.kuaishou.com/abc','kuaishou'),
 ('https://x.com/writer/status/123','twitter'),('https://writer.substack.com/p/post','substack'),
])
def test_podcast_and_video_families_have_distinct_sources(url,expected):
    detected=podcast_platform(url) or video_platform(url)
    assert detected==expected


@pytest.mark.parametrize('url',[
 'https://example.com/?next=https://youtube.com/watch?v=abcdefghijk',
 'https://podcasts.apple.com.evil.example/podcast/id123',
 'https://example.com/podcasts.apple.com/123',
 'https://youtube.com.evil.example/watch?v=abcdefghijk',
])
def test_other_hostnames_and_query_strings_do_not_claim_a_platform(url):
    assert podcast_platform(url)==''
    assert video_platform(url)=='web'
    assert normalize_video_url(url,'youtube')==url


@pytest.mark.asyncio
@pytest.mark.parametrize('form',[False,True])
async def test_known_video_host_wins_over_an_incorrect_submitted_category(client,monkeypatch,form):
    import api.routers.video_notes as routes
    from video_task_db import get_video_task_db
    enqueue=AsyncMock();monkeypatch.setattr(routes,'enqueue_video_note',enqueue)
    data={'url':'https://www.youtube.com/watch?v=abcdefghijk','platform':'bilibili'}
    response=await client.post('/api/video-notes/generate',data=data) if form else await client.post('/api/video-notes/generate-json',json=data)
    assert response.status_code==200
    task=get_video_task_db().get_task(response.json()['task_id'],'local')
    assert task['platform']=='youtube'


@pytest.mark.asyncio
@pytest.mark.parametrize('form',[False,True])
async def test_reimport_corrects_existing_owned_category_without_duplicating_the_task(client,monkeypatch,form):
    import api.routers.video_notes as routes
    from video_task_db import get_video_task_db
    db=get_video_task_db()
    url='https://www.youtube.com/watch?v=abcdefghijk'
    task_id=db.create_task({'url':url,'platform':'bilibili','user_id':'local','status':'failed'})
    monkeypatch.setattr(routes,'enqueue_video_note',AsyncMock())
    data={'url':url,'platform':'bilibili'}
    response=await client.post('/api/video-notes/generate',data=data) if form else await client.post('/api/video-notes/generate-json',json=data)
    assert response.status_code==200
    assert response.json()['task_id']==task_id
    assert db.get_task(task_id,'local')['platform']=='youtube'
