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
