from pathlib import Path
from unittest.mock import Mock
import pytest
from social_content import SocialContent, SocialSourceError
import social_downloader as downloader


def test_multiple_audio_attachments_are_downloaded_and_joined_in_order(monkeypatch,tmp_path):
    source=SocialContent('twitter','https://x.com/i/status/1','Post','Original caption',media=[
        {'url':'https://video.twimg.com/one.mp4','kind':'video'},{'url':'https://video.twimg.com/two.mp4','kind':'video'}])
    monkeypatch.setattr(downloader,'public_media_target',lambda url:url)
    monkeypatch.setattr(downloader,'VIDEO_AUDIO_DIR',tmp_path)
    native=Mock();native.download_audio.side_effect=[tmp_path/'first.mp3',tmp_path/'second.mp3']
    factory=Mock(return_value=native);monkeypatch.setattr(downloader,'YtdlpDownloader',factory)
    commands=[]
    def run(command,**kwargs):
        commands.append(command)
        manifest=Path(command[command.index('-i')+1]).read_text()
        assert manifest.index('first.mp3')<manifest.index('second.mp3')
    monkeypatch.setattr(downloader,'run_media_process',run)
    path=downloader.SocialDownloader(source).download_audio(source.url,'task')
    assert path==tmp_path/'task.mp3'
    assert native.download_audio.call_count==2
    assert factory.call_args.kwargs['use_saved_cookies'] is False
    assert len(commands)==1 and not list(tmp_path.glob('*_concat.txt'))


def test_attachment_failure_does_not_skip_to_later_attachments(monkeypatch,tmp_path):
    source=SocialContent('twitter','https://x.com/i/status/1','Post','Caption',media=[
        {'url':'https://video.twimg.com/one.mp4','kind':'video'},{'url':'https://video.twimg.com/two.mp4','kind':'video'}])
    monkeypatch.setattr(downloader,'public_media_target',lambda url:url)
    native=Mock();native.download_audio.return_value=None
    monkeypatch.setattr(downloader,'YtdlpDownloader',lambda *a,**k:native)
    with pytest.raises(SocialSourceError,match='Attachment 1'):downloader.SocialDownloader(source).download_audio(source.url,'task')
    native.download_audio.assert_called_once()


def test_audio_only_posts_do_not_request_video_or_fabricate_screenshots():
    source=SocialContent('substack','https://writer.substack.com/p/audio','Audio','Notes',media=[{'url':'https://api.substack.com/audio.mp3','kind':'audio'}])
    assert downloader.SocialDownloader(source).download_video(source.url,'task') is None


def test_existing_screenshot_recovery_resolves_the_same_ordered_social_media(monkeypatch):
    source=SocialContent('twitter','https://x.com/i/status/1','Post','Caption',media=[{'url':'https://video.twimg.com/one.mp4','kind':'video'}])
    resolve=Mock(return_value=source);monkeypatch.setattr(downloader,'resolve_social_content',resolve)
    resolved=Mock();resolved.download_video.return_value=Path('/tmp/combined.mp4')
    factory=Mock(return_value=resolved);monkeypatch.setattr(downloader,'SocialDownloader',factory)
    from video_downloader import get_downloader
    existing=get_downloader('twitter')
    assert existing.download_video(source.url,'task')==Path('/tmp/combined.mp4')
    resolve.assert_called_once_with(source.url);factory.assert_called_once_with(source)


def test_generic_media_is_fetched_once_with_pinning_and_ffmpeg_cannot_open_network_protocols(monkeypatch,tmp_path):
    from content_sources import ContentDocument
    from public_content_fetch import PublicResponse
    import social_downloader as module
    from unittest.mock import Mock
    monkeypatch.setattr(module,'VIDEO_AUDIO_DIR',tmp_path/'audio');monkeypatch.setattr(module,'VIDEO_DIR',tmp_path/'video')
    source=ContentDocument('web','https://cdn.example/source.mp4','Original recording','Original recording',media=[{'url':'https://cdn.example/source.mp4','kind':'video','duration':0}],content_type='video')
    calls=[]
    def fetch(url,**kwargs):
        calls.append(url);kwargs['sink'].write(b'Synthetic media bytes')
        return PublicResponse(url,'video/mp4',b'',{})
    monkeypatch.setattr('public_content_fetch.fetch_public',fetch)
    process=Mock();monkeypatch.setattr(module,'run_media_process',process)
    downloader=module.SocialDownloader(source)
    downloader.download_audio(source.url,'owned')
    downloader.download_video(source.url,'owned')
    assert calls==['https://cdn.example/source.mp4']
    for call in process.call_args_list:
        args=call.args[0]
        assert args[args.index('-protocol_whitelist')+1]=='file,pipe'
        assert not args[args.index('-i')+1].startswith('https:')
        assert 'hls' not in args[args.index('-format_whitelist')+1]
    assert downloader._public_source.exists()
    downloader.cleanup()
    assert not list((tmp_path/'audio').glob('*_source.media'))


def test_cancel_during_public_download_removes_partial_file_without_transcoding(monkeypatch,tmp_path):
    from api.routers.video_notes import VideoCancelledException
    monkeypatch.setattr(downloader,'VIDEO_AUDIO_DIR',tmp_path)
    source=SocialContent('web','https://cdn.example/audio.mp3','Recording','Original',
        media=[{'url':'https://cdn.example/audio.mp3','kind':'audio'}])
    def fetch(url,**kwargs):
        kwargs['sink'].write(b'partial')
        kwargs['progress_callback'](7,100)
        raise AssertionError('Cancellation must stop the stream')
    monkeypatch.setattr('public_content_fetch.fetch_public',fetch)
    process=Mock();monkeypatch.setattr(downloader,'run_media_process',process)
    def progress(value,message):
        if value>0: raise VideoCancelledException('Cancelled')
    with pytest.raises(VideoCancelledException):
        downloader.SocialDownloader(source).download_audio(source.url,'cancelled',progress_callback=progress)
    assert not list(tmp_path.iterdir())
    process.assert_not_called()
