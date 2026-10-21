from io import BytesIO
from unittest.mock import Mock
import pytest
from PIL import Image
from api import media


def image_bytes():
    stream=BytesIO();Image.new('RGB',(2400,1600),'blue').save(stream,format='JPEG');return stream.getvalue()


@pytest.mark.asyncio
async def test_existing_cloud_preview_never_downloads_original(tmp_path,monkeypatch):
    monkeypatch.setattr(media,'DATA_DIR',tmp_path)
    storage=Mock();storage.download.return_value=b'prepared-preview'
    assert await media.load_preview('screenshots','task_1.jpg',storage)==b'prepared-preview'
    storage.download.assert_called_once_with('previews/task_1.jpg.webp')
    storage.upload.assert_not_called()
    assert await media.load_preview('screenshots','task_1.jpg',storage)==b'prepared-preview'
    assert storage.download.call_count==1


@pytest.mark.asyncio
async def test_missing_preview_is_generated_once_and_original_unchanged(tmp_path,monkeypatch):
    monkeypatch.setattr(media,'DATA_DIR',tmp_path)
    original=image_bytes();storage=Mock()
    class Missing(Exception):code='NoSuchKey'
    storage.download.side_effect=lambda name:original if name=='task.jpg' else (_ for _ in ()).throw(Missing())
    result=await media.load_preview('screenshots','task.jpg',storage)
    assert Image.open(BytesIO(result)).size==(1000,667)
    assert await media.load_preview('screenshots','task.jpg',storage)==result
    assert storage.upload.call_count==1
    assert storage.upload.call_args.args[:2]==('previews/task.jpg.webp',result)
    assert storage.download.call_count==2


@pytest.mark.asyncio
async def test_preview_outage_does_not_trigger_original_download(tmp_path,monkeypatch):
    monkeypatch.setattr(media,'DATA_DIR',tmp_path)
    storage=Mock();storage.download.side_effect=TimeoutError()
    with pytest.raises(TimeoutError):await media.load_preview('screenshots','task.jpg',storage)
    storage.download.assert_called_once()


@pytest.mark.asyncio
async def test_backfill_skips_existing_previews_and_creates_only_missing(tmp_path,monkeypatch):
    import asyncio
    monkeypatch.setattr(media,'DATA_DIR',tmp_path)
    monkeypatch.setattr(media,'USE_SUPABASE',True)
    storage=Mock();client=Mock();client.storage.from_.return_value=storage
    storage.list.side_effect=[[{'name':'existing.jpg'},{'name':'old.jpg'}],[]]
    class Missing(Exception):code='NoSuchKey'
    storage.info.side_effect=[{},Missing()]
    storage.download.return_value=image_bytes()
    monkeypatch.setattr('api.supabase_client.get_supabase_admin_client',lambda:client)
    async def stop_after_sweep(seconds):
        if seconds==3600:raise asyncio.CancelledError()
    monkeypatch.setattr(media.asyncio,'sleep',stop_after_sweep)
    with pytest.raises(asyncio.CancelledError):await media.backfill_previews()
    storage.download.assert_called_once_with('old.jpg')
    assert storage.upload.call_count==1
    assert storage.upload.call_args.args[0]=='previews/old.jpg.webp'
