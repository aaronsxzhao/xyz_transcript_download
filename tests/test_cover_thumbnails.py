"""Public covers persist across restarts without widening private media access."""
import asyncio
import io
from unittest.mock import AsyncMock
import httpx
import pytest
from fastapi import HTTPException
from PIL import Image
from api import covers


def image():
    output=io.BytesIO();Image.new('RGB',(1600,900),'navy').save(output,format='JPEG');return output.getvalue()


@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setattr(covers,'DATA_DIR',tmp_path)
    monkeypatch.setattr(covers,'_pending',{})
    monkeypatch.setattr(covers,'_failures',{})
    monkeypatch.setattr(covers,'_slots',asyncio.Semaphore(6))
    monkeypatch.setattr(covers,'USE_SUPABASE',False)


def test_provider_hosts_and_resized_webp():
    assert covers.validate_url('https://bts-image.xyzcdn.net/cover')=='bts-image.xyzcdn.net'
    assert covers.validate_url('https://i2.hdslb.com/cover')=='i2.hdslb.com'
    for bad in ['http://127.0.0.1/a','https://image.xyzcdn.net.attacker.invalid/a','https://user:pass@image.xyzcdn.net/a','https://image.xyzcdn.net:8080/a','https://project.supabase.co/storage/v1/object/public/thumbnails/private.jpg']:
        with pytest.raises(HTTPException):covers.validate_url(bad)
    content=covers.make_thumbnail(image())
    with Image.open(io.BytesIO(content)) as preview:
        assert preview.format=='WEBP' and max(preview.size)==480
    assert len(content)<len(image())


def test_article_and_full_resolution_images_do_not_share_small_cover_cache():
    source=io.BytesIO();Image.new('RGB',(2400,1800),'navy').save(source,format='JPEG')
    url='https://pbs.twimg.com/chart.jpg'
    assert len({covers.cache_key(url,size) for size in ('cover','article','original')}) == 3
    for size,expected in [('cover',480),('article',1600),('original',2400)]:
        with Image.open(io.BytesIO(covers.make_thumbnail(source.getvalue(),size))) as output:
            assert max(output.size)==expected
    with pytest.raises(HTTPException): covers.cache_key(url,'unbounded')


@pytest.mark.asyncio
async def test_article_proxy_variants_persist_independently_and_reuse_cached_bytes(monkeypatch):
    origin=AsyncMock(return_value=covers.make_thumbnail(image(),'article'))
    monkeypatch.setattr(covers,'_origin',origin)
    url='https://pbs.twimg.com/diagram.jpg'
    assert (await covers.load_cover(url,variant='article'))[1]=='origin'
    assert (await covers.load_cover(url,variant='article'))[1]=='disk'
    assert origin.await_count==1 and origin.call_args.args==(url,'article')
    await covers.load_cover(url,variant='original')
    assert origin.await_count==2


@pytest.mark.asyncio
async def test_concurrent_reads_persist_once_and_survive_local_cache_loss(monkeypatch):
    content=covers.make_thumbnail(image())
    monkeypatch.setattr(covers,'_cloud',lambda:True)
    storage=AsyncMock(return_value=None);origin=AsyncMock(return_value=content)
    monkeypatch.setattr(covers,'_storage',storage);monkeypatch.setattr(covers,'_origin',origin)
    url='https://image.xyzcdn.net/cover'
    result=await asyncio.gather(*(covers.load_cover(url) for _ in range(5)))
    assert all(row[0]==content for row in result)
    assert origin.await_count==1 and storage.await_count==2
    assert storage.call_args.args[1]==content
    assert (await covers.load_cover(url))[1]=='disk'
    assert storage.await_count==2
    key=covers.cache_key(url);path,marker=covers._paths(key);path.unlink();marker.unlink()
    storage.reset_mock();storage.return_value=content
    assert (await covers.load_cover(url))[1]=='storage'
    assert origin.await_count==1 and storage.await_count==1


@pytest.mark.asyncio
async def test_failed_persistence_retries_without_refetching_source(monkeypatch):
    content=covers.make_thumbnail(image());origin=AsyncMock(return_value=content)
    monkeypatch.setattr(covers,'_cloud',lambda:True);monkeypatch.setattr(covers,'_origin',origin)
    storage=AsyncMock(side_effect=[None,TimeoutError('Storage')]);monkeypatch.setattr(covers,'_storage',storage)
    url='https://image.xyzcdn.net/retry'
    assert (await covers.load_cover(url))[0]==content
    storage.side_effect=None;storage.return_value=None
    await covers.load_cover(url,persist=True)
    assert origin.await_count==1
    assert covers._paths(covers.cache_key(url))[1].exists()


@pytest.mark.asyncio
async def test_origin_sets_bilibili_headers_and_validates_redirects(respx_mock):
    route=respx_mock.get('https://i0.hdslb.com/cover').mock(return_value=httpx.Response(200,content=image()))
    result=await covers._origin('https://i0.hdslb.com/cover')
    assert result.startswith(b'RIFF')
    assert route.calls[0].request.headers['referer']=='https://www.bilibili.com/'
    assert 'authorization' not in route.calls[0].request.headers
    respx_mock.get('https://image.xyzcdn.net/redirect').mock(return_value=httpx.Response(302,headers={'Location':'http://127.0.0.1/private'}))
    with pytest.raises(HTTPException):await covers._origin('https://image.xyzcdn.net/redirect')


@pytest.mark.asyncio
async def test_failures_are_not_cached_as_success_and_allow_a_later_retry(monkeypatch):
    origin=AsyncMock(side_effect=ValueError('Not an image'));monkeypatch.setattr(covers,'_origin',origin)
    url='https://image.xyzcdn.net/failure'
    with pytest.raises(HTTPException):await covers.load_cover(url)
    with pytest.raises(HTTPException) as error:await covers.load_cover(url)
    assert error.value.status_code==503 and origin.await_count==1
    covers._failures.clear();origin.side_effect=None;origin.return_value=covers.make_thumbnail(image())
    assert (await covers.load_cover(url))[0].startswith(b'RIFF')


@pytest.mark.asyncio
async def test_endpoint_cache_validator_and_private_domain_rejection(client,monkeypatch):
    origin=AsyncMock(return_value=covers.make_thumbnail(image()));monkeypatch.setattr(covers,'_origin',origin)
    response=await client.get('/api/image-proxy',params={'url':'https://image.xyzcdn.net/etag'})
    assert response.status_code==200 and response.headers['content-type']=='image/webp'
    assert response.headers['x-artwork-cache']=='origin'
    cached=await client.get('/api/image-proxy',params={'url':'https://image.xyzcdn.net/etag'},headers={'If-None-Match':response.headers['etag']})
    assert cached.status_code==304 and cached.headers['x-artwork-cache']=='disk'
    assert origin.await_count==1
    denied=await client.get('/api/image-proxy',params={'url':'https://project.supabase.co/storage/v1/object/public/thumbnails/private.jpg'})
    assert denied.status_code==403 and denied.headers['cache-control']=='no-store'


def test_library_private_thumbnail_remains_signed(monkeypatch):
    from api import media
    from api.routers.library import page_rows
    monkeypatch.setattr(media,'USE_SUPABASE',True)
    monkeypatch.setattr(media,'SUPABASE_URL','https://project.supabase.co')
    monkeypatch.setenv('MEDIA_SIGNING_KEY','artwork-test');media._signing_key.cache_clear()
    result=page_rows([{'id':'owned','kind':'video','thumbnail':'https://project.supabase.co/storage/v1/object/public/thumbnails/owned.jpg','sort_key':'a'}],40)
    url=result['items'][0]['thumbnail']
    assert url.startswith('/data/thumbnails/owned.jpg?') and 'signature=' in url
    media._signing_key.cache_clear()

@pytest.mark.asyncio
async def test_storage_uses_private_authenticated_object_and_idempotent_upload(monkeypatch,respx_mock):
    monkeypatch.setattr(covers,'SUPABASE_URL','https://storage.example.test')
    monkeypatch.setattr(covers,'SUPABASE_SERVICE_KEY','synthetic-server-key')
    url='https://storage.example.test/storage/v1/object/thumbnails/covers-v1/test.webp'
    content=covers.make_thumbnail(image())
    get=respx_mock.get(url).mock(return_value=httpx.Response(200,content=content))
    assert await covers._storage('test')==content
    post=respx_mock.post(url).mock(return_value=httpx.Response(200,json={}))
    await covers._storage('test',content)
    assert get.calls[0].request.headers['Authorization']=='Bearer synthetic-server-key'
    assert post.calls[0].request.headers['x-upsert']=='true'
    assert post.calls[0].request.content==content


@pytest.mark.asyncio
async def test_youtube_missing_large_artwork_uses_available_preview(respx_mock):
    respx_mock.get('https://i.ytimg.com/vi/test/maxresdefault.jpg').mock(return_value=httpx.Response(404))
    smaller=respx_mock.get('https://i.ytimg.com/vi/test/hqdefault.jpg').mock(return_value=httpx.Response(200,content=image()))
    assert (await covers._origin('https://i.ytimg.com/vi/test/maxresdefault.jpg')).startswith(b'RIFF')
    assert smaller.called
