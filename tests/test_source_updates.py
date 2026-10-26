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


def test_x_legacy_post_resolves_author_and_ignores_foreign_posts_and_pinned_order(monkeypatch):
    monkeypatch.setattr(updates,'_json',Mock(return_value={'tweet':{'author':{'screen_name':'writer'}}}))
    entries=[{'content':{'tweet':{'id_str':ident,'user':{'screen_name':author},'full_text':title}}} for ident,author,title in [('100','writer','Pinned'),('300','other','Other author'),('200','writer','New post')]]
    html='<script id="__NEXT_DATA__" type="application/json">'+json.dumps({'props':{'pageProps':{'timeline':{'entries':entries}}}})+'</script>'
    fetch=Mock(return_value=response(html,'https://syndication.twitter.com'))
    monkeypatch.setattr(updates,'fetch_public',fetch)
    rows=updates.list_author_updates('https://x.com/i/status/99','twitter')
    assert [r['url'] for r in rows]==['https://x.com/i/status/200','https://x.com/i/status/100']
    assert fetch.call_args.args[0].endswith('/screen-name/writer')


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
