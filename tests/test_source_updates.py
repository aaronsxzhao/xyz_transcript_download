"""Public discovery preserves ownership, platform scope and truthful failures."""
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
import source_updates as updates
from social_content import SocialSourceError


def response(content,url): return NS(content=content.encode(),url=url)


def test_publication_feed_preserves_dates_orders_newest_and_deduplicates(monkeypatch):
    xml='<rss><channel>' + ''.join(f'<item><title>{title}</title><link>https://writer.substack.com/p/{slug}?utm_source=rss</link><pubDate>{date}</pubDate></item>' for title,slug,date in [
        ('Pinned','old','Mon, 01 Jan 2024 00:00:00 GMT'),('Latest','new','Mon, 26 Oct 2026 00:00:00 GMT'),('Latest','new','Mon, 26 Oct 2026 00:00:00 GMT')])+'</channel></rss>'
    fetch=Mock(return_value=response(xml,'https://writer.substack.com/feed'))
    monkeypatch.setattr(updates,'fetch_public',fetch)
    rows=updates.list_author_updates('https://writer.substack.com/p/imported','substack')
    assert [r['url'] for r in rows]==['https://writer.substack.com/p/new','https://writer.substack.com/p/old']
    assert rows[0]['published_at'].startswith('2026-10-26')
    assert fetch.call_args.args[0]=='https://writer.substack.com/feed'


@pytest.mark.parametrize('html',['<html>Sign in</html>','<rss/>'])
def test_restricted_or_invalid_feed_is_not_a_successful_empty_check(monkeypatch,html):
    monkeypatch.setattr(updates,'fetch_public',lambda *a,**k:response(html,'https://writer.substack.com/feed'))
    with pytest.raises(SocialSourceError): updates.list_author_updates('https://writer.substack.com','substack')


@pytest.mark.parametrize('field', ['tweet', 'status'])
def test_x_legacy_post_resolves_author_and_ignores_foreign_posts_and_pinned_order(monkeypatch, field):
    metadata=Mock(return_value={field:{'author':{'screen_name':'writer'}}})
    monkeypatch.setattr(updates,'_json',metadata)
    entries=[{'content':{'tweet':{'id_str':ident,'user':{'screen_name':author},'full_text':title}}} for ident,author,title in [('100','writer','Pinned'),('300','other','Other author'),('200','writer','New post')]]
    html='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'timeline':{'entries':entries}}}})+'</script>'
    fetch=Mock(return_value=response(html,'https://syndication.twitter.com'))
    monkeypatch.setattr(updates,'fetch_public',fetch)
    rows=updates.list_author_updates('https://x.com/i/status/99','twitter')
    assert [r['url'] for r in rows]==['https://x.com/i/status/200','https://x.com/i/status/100']
    assert fetch.call_args.args[0].endswith('/screen-name/writer')
    assert metadata.call_args.args[0]=='https://api.fxtwitter.com/2/status/99'


def test_x_restricted_timeline_is_reported_and_not_replaced_with_an_empty_list(monkeypatch):
    monkeypatch.setattr(updates,'fetch_public',lambda *a,**k:response('<html>Sign in</html>','https://syndication.twitter.com'))
    with pytest.raises(SocialSourceError,match='public author timeline'):
        updates.list_author_updates('https://x.com/writer','twitter')


def test_notes_public_listing_only_returns_the_same_authors_notes(monkeypatch):
    monkeypatch.setattr(updates,'fetch_public',lambda *a,**k:response('<a href="/@writer/note/c-2">Own note</a><a href="/@other/note/c-3">Other note</a>','https://substack.com/@writer'))
    assert updates.list_author_updates('https://substack.com/@writer/note/c-1','substack')==[{'url':'https://substack.com/@writer/note/c-2','title':'Own note','channel_url':'https://substack.com/@writer'}]


@pytest.mark.parametrize('url',['http://x.com/writer','https://x.com.evil.example/writer','https://user:secret@x.com/writer','https://x.com:444/writer'])
def test_invalid_author_destination_does_not_issue_a_request(monkeypatch,url):
    fetch=Mock();monkeypatch.setattr(updates,'fetch_public',fetch)
    with pytest.raises(SocialSourceError):updates.list_author_updates(url,'twitter')
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_channel_scan_is_platform_and_owner_scoped_deduplicated_and_idempotent(monkeypatch):
    from api.routers.video_notes import check_channels_for_updates
    db=Mock(); db.get_distinct_channels.return_value=[
        {'channel':'Writer','platform':p,'channel_url':url} for p,url in [('twitter','https://x.com/i/status/1'),('twitter','https://x.com/writer'),('youtube','https://youtube.com/@writer')]]
    saved=[]
    db.get_existing_urls.side_effect=lambda urls,owner:{row['url'] for row in saved}
    db.create_task.side_effect=lambda row:saved.append(row) or 'new'
    listing=Mock(return_value=[{'url':'https://x.com/i/status/2','title':'New text'},{'url':'https://x.com/i/status/2','title':'Duplicate'}])
    monkeypatch.setattr(updates,'list_author_updates',listing)
    with patch('video_task_db.get_video_task_db',return_value=db):
        result=await check_channels_for_updates(channel='Writer',platform='twitter',request=None,user=NS(id='owner'))
        again=await check_channels_for_updates(channel='Writer',platform='twitter',request=None,user=NS(id='owner'))
    assert result['new_videos']==1 and result['channels_checked']==1 and result['channels_failed']==0
    assert again['new_videos']==0 and len(saved)==1
    assert saved[0]['user_id']=='owner' and saved[0]['status']=='discovered' and saved[0]['platform']=='twitter'
    assert listing.call_count==2 and listing.call_args.args==('https://x.com/writer','twitter')
    db.get_distinct_channels.assert_called_with('owner')
    assert all(call.args[1]=='owner' for call in db.get_existing_urls.call_args_list)


@pytest.mark.asyncio
async def test_source_failure_returns_partial_results_instead_of_all_caught_up(monkeypatch):
    from api.routers.video_notes import check_channels_for_updates
    db=Mock();db.get_distinct_channels.return_value=[{'channel':'Blocked','platform':'twitter','channel_url':'https://x.com/blocked'}]
    monkeypatch.setattr(updates,'list_author_updates',Mock(side_effect=SocialSourceError('Public timeline restricted')))
    with patch('video_task_db.get_video_task_db',return_value=db):
        result=await check_channels_for_updates(channel=None,platform='twitter',request=None,user=NS(id='owner'))
    assert result['channels_checked']==0 and result['channels_failed']==1
    assert result['failures'][0]['message']=='Public timeline restricted'
    db.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_substack_notes_and_publication_with_the_same_author_name_keep_both_update_sources(monkeypatch):
    from api.routers.video_notes import check_channels_for_updates
    db=Mock();db.get_distinct_channels.return_value=[{'channel':'Writer','platform':'substack','channel_url':url} for url in ['https://writer.substack.com/p/one','https://writer.substack.com/p/two','https://substack.com/@writer/note/c-1']]
    listing=Mock(return_value=[]);monkeypatch.setattr(updates,'list_author_updates',listing)
    with patch('video_task_db.get_video_task_db',return_value=db):
        result=await check_channels_for_updates(channel='Writer',platform='substack',request=None,user=NS(id='owner'))
    assert result['channels_checked']==2 and listing.call_count==2


@pytest.mark.asyncio
async def test_spotify_feed_failure_is_exposed_by_global_scan():
    from api.main import _scan_podcasts_for_new_episodes
    db=Mock();db.get_all_podcasts.return_value=[NS(platform='spotify',feed_url='https://feed.example/rss',pid='show',title='Show')]
    report=[]
    with patch('apple_podcasts_client.get_episodes_from_feed',side_effect=ValueError('Unreadable feed')):
        assert await _scan_podcasts_for_new_episodes(db,report=report)==(0,[])
    assert report and report[0]['source']=='Show'
    db.update_podcast_checked.assert_not_called()


@pytest.mark.asyncio
async def test_paged_updates_check_one_source_and_continue_after_restricted_source(monkeypatch):
    from api.routers.video_notes import check_channels_for_updates
    db=Mock();db.get_distinct_channels.return_value=[
        {'channel':name,'platform':'twitter','channel_url':f'https://x.com/{name}'} for name in ['Zed','Alice']]
    db.save_discoveries.return_value=2
    listing=Mock(side_effect=[SocialSourceError('Public timeline restricted'),[{'url':'https://x.com/i/status/21','title':'New'}]])
    monkeypatch.setattr(updates,'list_author_updates',listing)
    with patch('video_task_db.get_video_task_db',return_value=db):
        first=await check_channels_for_updates(channel=None,platform='twitter',paged=True,user=NS(id='owner'))
        assert first['channels_failed']==1 and first['channels_processed']==1 and first['channels_total']==2
        assert listing.call_count==1 and first['next_cursor']
        # A canonical author URL replacing an old post URL must not reset paging.
        db.get_distinct_channels.return_value[0]['channel_url']='https://x.com/Zed/status/7'
        last=await check_channels_for_updates(channel=None,platform='twitter',paged=True,cursor=first['next_cursor'],user=NS(id='owner'))
    assert last['new_videos']==2 and last['channels_checked']==1 and last['next_cursor'] is None
    assert last['channels_processed']==2
    db.save_discoveries.assert_called_once()
    assert db.save_discoveries.call_args.args[1]=='owner'
    db.create_task.assert_not_called()


@pytest.mark.asyncio
async def test_paged_cursor_cannot_skip_another_owners_sources():
    from api.routers.video_notes import check_channels_for_updates
    from fastapi import HTTPException
    db=Mock();db.get_distinct_channels.return_value=[{'channel':name,'platform':'twitter','channel_url':f'https://x.com/{name}'} for name in ['Alice','Zed']]
    with patch('video_task_db.get_video_task_db',return_value=db),patch.object(updates,'list_author_updates',return_value=[]):
        first=await check_channels_for_updates(channel=None,platform='twitter',paged=True,user=NS(id='owner'))
        with pytest.raises(HTTPException) as exc:
            await check_channels_for_updates(channel=None,platform='twitter',paged=True,cursor=first['next_cursor'],user=NS(id='other'))
    assert exc.value.status_code==409


def test_discovery_batch_is_owner_scoped_idempotent_and_preserves_completed_content(tmp_path):
    from video_task_db import VideoTaskDB
    with patch('video_task_db.USE_SUPABASE',False): db=VideoTaskDB(tmp_path/'video.db')
    old=db.create_task({'url':'https://x.com/i/status/1','user_id':'owner','status':'success','title':'Read me'})
    db.update_task(old,{'markdown':'Full saved article'})
    db.create_task({'url':'https://x.com/i/status/2','user_id':'other','status':'success'})
    rows=[{'url':f'https://x.com/i/status/{i}','title':'Discovered','status':'discovered','formats':['summary'],'published_at':'2026-10-26'} for i in [1,2,2]]
    assert db.save_discoveries(rows,'owner')==1
    assert db.save_discoveries(rows,'owner')==0
    assert db.get_task(old,'owner')['markdown']=='Full saved article'
    assert db.get_task(old,'owner')['status']=='success'
    assert db.get_task(old,'owner')['published_at']=='2026-10-26'
    assert db.get_task_by_url(rows[1]['url'],'other')['status']=='success'
    assert db.get_task_by_url(rows[1]['url'],'owner')['formats']==['summary']


def test_cloud_discovery_uses_one_read_and_one_insert_for_fifteen_items():
    from api.source_discovery import save_discoveries
    client=Mock();query=client.table.return_value
    query.select.return_value.eq.return_value.in_.return_value.execute.return_value=NS(data=[])
    query.upsert.return_value.execute.return_value=NS(data=[{'id':str(i)} for i in range(15)])
    backend=NS(_sb=NS(client=client))
    rows=[{'url':f'https://x.com/i/status/{i}','status':'discovered'} for i in range(15)]
    assert save_discoveries(backend,rows,'owner')==15
    query.select.assert_called_once_with('id,url,published_at')
    query.upsert.assert_called_once()
    payload=query.upsert.call_args.args[0]
    assert len(payload)==15 and all(row['user_id']=='owner' for row in payload)
    assert query.upsert.call_args.kwargs=={'on_conflict':'id','ignore_duplicates':True}
    query.update.assert_not_called()


def test_cloud_channel_discovery_keeps_platforms_and_publication_variants_beyond_first_page():
    from api.supabase_db import SupabaseDatabase
    db=object.__new__(SupabaseDatabase);db.client=Mock()
    query=db.client.table.return_value
    query.select.return_value.eq.return_value.neq.return_value.order.return_value=query
    first=[{'channel':'Same name','platform':'youtube','channel_url':'https://youtube.com/@writer'}]*1000
    second=[{'channel':'Same name','platform':'twitter','channel_url':'https://x.com/writer'},
            {'channel':'Same name','platform':'substack','channel_url':'https://writer.substack.com'},
            {'channel':'Same name','platform':'substack','channel_url':'https://substack.com/@writer'}]
    query.range.return_value.execute.side_effect=[NS(data=first),NS(data=second)]
    rows=db.get_distinct_video_channels('owner')
    assert len(rows)==4 and {row['platform'] for row in rows}=={'youtube','twitter','substack'}
    assert query.range.call_args_list[1].args==(1000,1999)
    query.select.return_value.eq.assert_called_with('user_id','owner')


@pytest.mark.asyncio
async def test_lost_save_acknowledgement_keeps_owner_lock_until_write_finishes(monkeypatch):
    import asyncio
    import threading
    from api.routers import video_notes
    from fastapi import HTTPException
    started=threading.Event();release=threading.Event()
    db=Mock();db.get_distinct_channels.return_value=[{'channel':'Writer','platform':'twitter','channel_url':'https://x.com/writer'}]
    def save(*args):
        started.set();release.wait(2);return 1
    db.save_discoveries.side_effect=save
    wait_for=asyncio.wait_for
    async def lose_ack(awaitable,timeout):
        if timeout==25:
            await asyncio.to_thread(started.wait,1)
            raise TimeoutError()
        return await wait_for(awaitable,timeout)
    monkeypatch.setattr(updates,'list_author_updates',lambda *a,**k:[{'url':'https://x.com/i/status/1'}])
    monkeypatch.setattr(video_notes.asyncio,'wait_for',lose_ack)
    with patch('video_task_db.get_video_task_db',return_value=db):
        try:
            result=await video_notes.check_channels_for_updates(channel=None,platform='twitter',paged=True,user=NS(id='owner'))
            assert result['channels_failed']==1 and 'owner' in video_notes._channel_checks
            with pytest.raises(HTTPException) as exc:
                await video_notes.check_channels_for_updates(channel=None,platform='twitter',paged=True,user=NS(id='owner'))
            assert exc.value.status_code==409
        finally:
            release.set()
            for _ in range(50):
                if 'owner' not in video_notes._channel_checks:break
                await asyncio.sleep(.01)
    assert 'owner' not in video_notes._channel_checks
    db.save_discoveries.assert_called_once()
