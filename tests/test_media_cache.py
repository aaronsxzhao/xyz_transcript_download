"""Image retries, caching and signatures must preserve private file access."""
import asyncio
import time
from unittest.mock import Mock, patch

import pytest


def test_signed_urls_are_stable_within_a_day(tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, 'USE_SUPABASE', True)
    monkeypatch.setenv('MEDIA_SIGNING_KEY', 'test-cache-key')
    media._signing_key.cache_clear()
    raw = '/data/screenshots/owned_frame.jpg'
    with patch.object(media.time, 'time', return_value=2000000000):
        first = media.sign_media_urls(raw, 'owned')
    with patch.object(media.time, 'time', return_value=2000000001):
        assert media.sign_media_urls(raw, 'owned') == first
    assert media.sign_media_urls(raw, 'other') == raw
    media._signing_key.cache_clear()


@pytest.mark.asyncio
async def test_cloud_media_deduplicates_and_reuses_private_cache(tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, 'DATA_DIR', tmp_path)
    def fetch(_filename):
        time.sleep(.03)
        return b'private-image'
    download = Mock(side_effect=fetch)
    results = await asyncio.gather(*(media.load_cloud_media('screenshots', 'owned_frame.jpg', download) for _ in range(6)))
    assert results == [b'private-image'] * 6
    assert await media.load_cloud_media('screenshots', 'owned_frame.jpg', download) == b'private-image'
    download.assert_called_once()
    assert not (tmp_path / 'screenshots' / 'owned_frame.jpg').exists()
    cached = tmp_path / '.media-cache' / 'screenshots' / 'owned_frame.jpg'
    import os
    os.utime(cached, (0, 0))
    assert await media.load_cloud_media('screenshots', 'owned_frame.jpg', download) == b'private-image'
    assert download.call_count == 2


@pytest.mark.asyncio
async def test_failed_image_download_can_retry(tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, 'DATA_DIR', tmp_path)
    download = Mock(side_effect=[RuntimeError('Storage unavailable'), b'image'])
    with pytest.raises(RuntimeError):
        await media.load_cloud_media('screenshots', 'owned_frame.jpg', download)
    assert await media.load_cloud_media('screenshots', 'owned_frame.jpg', download) == b'image'


@pytest.mark.asyncio
async def test_disk_cache_still_requires_valid_signature(client, tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, 'DATA_DIR', tmp_path)
    await media.load_cloud_media('screenshots', 'owned_frame.jpg', lambda _: b'private-image')
    with patch('config.USE_SUPABASE', True):
        response = await client.get('/data/screenshots/owned_frame.jpg')
        assert response.status_code == 403
    assert (await client.get('/data/.media-cache/screenshots/owned_frame.jpg')).status_code == 404


@pytest.mark.asyncio
async def test_disconnected_waiter_does_not_cancel_shared_download(tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, 'DATA_DIR', tmp_path)
    download = Mock(side_effect=lambda _: (time.sleep(.04), b'image')[1])
    first = asyncio.create_task(media.load_cloud_media('screenshots', 'cancelled_frame.jpg', download))
    second = asyncio.create_task(media.load_cloud_media('screenshots', 'cancelled_frame.jpg', download))
    await asyncio.sleep(.005)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await second == b'image'
    download.assert_called_once()


def test_cache_is_bounded_and_disk_errors_do_not_hide_images(tmp_path, monkeypatch):
    import api.media as media
    monkeypatch.setattr(media, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(media, '_MEDIA_CACHE_BYTES', 8)
    for i in range(4):
        assert media._read_or_download('screenshots', f'frame_{i}.jpg', lambda _: b'1234') == b'1234'
    assert sum(p.stat().st_size for p in (tmp_path / '.media-cache').glob('*/*')) <= 8
    with patch.object(media.tempfile, 'NamedTemporaryFile', side_effect=OSError('disk full')):
        assert media._read_or_download('screenshots', 'new_frame.jpg', lambda _: b'image') == b'image'


def test_preview_is_smaller_preserves_source_and_bounds_pixels(tmp_path, monkeypatch):
    from io import BytesIO
    from PIL import Image
    from api import media
    monkeypatch.setattr(media, 'DATA_DIR', tmp_path)
    image=Image.effect_noise((2400,1600),64).convert('RGB')
    source=BytesIO(); image.save(source,format='PNG')
    original=source.getvalue()
    preview=media.image_preview(original)
    assert source.getvalue()==original
    assert len(preview)<len(original)*0.5
    with Image.open(BytesIO(preview)) as result:
        assert result.format=='WEBP'
        assert result.width<=1000 and result.height<=1000
    assert media.image_preview(original)==preview


@pytest.mark.asyncio
@pytest.mark.parametrize('missing,expected', [(False,503),(True,404)])
async def test_preview_separates_storage_outage_from_missing_file(client,tmp_path,monkeypatch,missing,expected):
    import api.media as media
    from storage3.exceptions import StorageApiError
    monkeypatch.setattr(media,'DATA_DIR',tmp_path)
    monkeypatch.setattr(media,'USE_SUPABASE',True)
    monkeypatch.setenv('MEDIA_SIGNING_KEY','preview-test-key'); media._signing_key.cache_clear()
    signed=media.sign_media_urls('/data/screenshots/owned_frame.jpg','owned')+'&preview=true'
    provider=Mock()
    provider.storage.from_.return_value.download.side_effect=StorageApiError('Not found','NoSuchKey',404) if missing else TimeoutError('Storage unavailable')
    with patch('config.USE_SUPABASE',True), patch('api.supabase_client.get_supabase_admin_client',return_value=provider):
        assert (await client.get('/data/screenshots/owned_frame.jpg?preview=true')).status_code==403
        provider.storage.from_.return_value.download.assert_not_called()
        response=await client.get(signed)
    assert response.status_code==expected
    assert 'no-store' in response.headers['cache-control']
    media._signing_key.cache_clear()
