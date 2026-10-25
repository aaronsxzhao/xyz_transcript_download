import io
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest
from PIL import Image
from api import article_images, covers, media
from public_content_fetch import PublicResponse


def test_images_are_signed_without_rewriting_links_code_or_stored_original(monkeypatch):
    monkeypatch.setenv('MEDIA_SIGNING_KEY','synthetic-article-key');media._signing_key.cache_clear()
    source='[Source](https://example.com/chart.png)\n\n![Chart](https://example.com/chart.png)\n\n```md\n![Code](https://example.com/chart.png)\n```'
    result=media.sign_media_urls({'id':'owned','platform':'web','style':'original','markdown':source,'thumbnail':'https://example.com/chart.png'})
    assert result['markdown'].count('/api/article-image?')==1
    assert '[Source](https://example.com/chart.png)' in result['markdown']
    assert '![Code](https://example.com/chart.png)' in result['markdown']
    assert result['thumbnail'].startswith('/api/article-image?')
    assert source.count('/api/article-image?')==0
    assert article_images.signed_article_image('http://127.0.0.1/private')==''
    media._signing_key.cache_clear()


@pytest.mark.asyncio
async def test_signed_images_reuse_cache_but_tampered_unsigned_and_private_targets_never_fetch(client,monkeypatch,tmp_path):
    monkeypatch.setenv('MEDIA_SIGNING_KEY','synthetic-article-key');media._signing_key.cache_clear()
    monkeypatch.setattr(covers,'DATA_DIR',tmp_path);monkeypatch.setattr(covers,'_cloud',lambda:False)
    monkeypatch.setattr(covers,'_pending',{});monkeypatch.setattr(covers,'_failures',{})
    output=io.BytesIO();Image.new('RGB',(1800,1200),'navy').save(output,format='JPEG')
    fetch=Mock(return_value=PublicResponse('https://example.com/chart.jpg','image/jpeg',output.getvalue(),{}))
    monkeypatch.setattr(article_images,'fetch_public',fetch)
    signed=article_images.signed_article_image('https://example.com/chart.jpg')
    first=await client.get(signed)
    assert first.status_code==200 and first.headers['x-artwork-cache']=='origin'
    second=await client.get(signed,headers={'If-None-Match':first.headers['etag']})
    assert second.status_code==304 and fetch.call_count==1
    assert (await client.get(signed.replace('example.com','different.example'))).status_code==403
    query=parse_qs(urlsplit(signed).query)
    query['url']=['http://127.0.0.1/private']
    assert (await client.get('/api/article-image',params={k:v[0] for k,v in query.items()})).status_code==403
    query['expires']=['1']
    assert (await client.get('/api/article-image',params={k:v[0] for k,v in query.items()})).status_code==403
    assert fetch.call_count==1
    media._signing_key.cache_clear()
