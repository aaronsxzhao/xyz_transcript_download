"""Screenshot repair must use the same public social adapters as generation."""
from pathlib import Path
from unittest.mock import Mock
import pytest


@pytest.mark.parametrize('platform,url',[
 ('twitter','https://x.com/i/status/123'),
 ('substack','https://writer.substack.com/p/video'),
 ('substack','https://publication.example/p/video'),
])
def test_social_video_repairs_use_the_existing_platform_downloader(monkeypatch,platform,url):
 from api.routers import maintenance
 name='repair-social_00-10.jpg';existing=set();report=Mock()
 monkeypatch.setattr(maintenance,'_frames',lambda *args:{name:10})
 monkeypatch.setattr(maintenance,'_existing',lambda:existing)
 monkeypatch.setattr(maintenance,'_save_report',report)
 manager=Mock();manager.get_cookie.return_value=''
 cookie=Mock(return_value=manager);monkeypatch.setattr('cookie_manager.get_cookie_manager',cookie)
 downloader=Mock();downloader.download_video.return_value=Path('/tmp/synthetic-social.mp4')
 factory=Mock(return_value=downloader);monkeypatch.setattr('video_downloader.get_downloader',factory)
 extract=Mock(side_effect=lambda *args:existing.add(name));monkeypatch.setattr('screenshot_extractor.extract_screenshots_batch',extract)
 db=Mock();db.get_task.return_value={'status':'success','error':''}
 monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
 maintenance._repair({'id':'repair-social','platform':platform,'url':url},'owner','repair-key')
 assert report.call_args.args[1]['status']=='completed'
 cookie.assert_called_once_with('owner')
 factory.assert_called_once_with(platform,'')
 downloader.download_video.assert_called_once_with(url,'repair-social',video_quality='360')
 assert extract.call_args.args[1]==[10]


@pytest.mark.parametrize('platform,url',[
 ('twitter','https://x.com.evil.example/i/status/123'),
 ('substack','https://example.com/not-a-post'),
 ('twitter','https://writer.substack.com/p/video'),
 ('substack','http://writer.substack.com/p/video'),
])
def test_source_family_and_https_checks_remain_in_place(monkeypatch,platform,url):
 from api.routers import maintenance
 monkeypatch.setattr(maintenance,'_frames',lambda *args:{'repair-social_00-10.jpg':10})
 monkeypatch.setattr(maintenance,'_existing',lambda:set())
 report=Mock();monkeypatch.setattr(maintenance,'_save_report',report)
 factory=Mock();monkeypatch.setattr('video_downloader.get_downloader',factory)
 maintenance._repair({'id':'repair-social','platform':platform,'url':url},'owner','repair-key')
 assert report.call_args.args[1]['status']=='failed'
 factory.assert_not_called()


def test_public_source_restrictions_keep_their_actionable_reason(monkeypatch):
 from api.routers import maintenance
 from social_content import SocialSourceError
 monkeypatch.setattr(maintenance,'_frames',lambda *args:{'repair-social_00-10.jpg':10})
 monkeypatch.setattr(maintenance,'_existing',lambda:set())
 report=Mock();monkeypatch.setattr(maintenance,'_save_report',report)
 manager=Mock();manager.get_cookie.return_value=''
 monkeypatch.setattr('cookie_manager.get_cookie_manager',lambda owner:manager)
 downloader=Mock();downloader.download_video.side_effect=SocialSourceError('This Substack post requires a subscription. Open the original post.')
 monkeypatch.setattr('video_downloader.get_downloader',lambda *args:downloader)
 maintenance._repair({'id':'repair-social','platform':'substack','url':'https://writer.substack.com/p/video'},'owner','repair-key')
 assert report.call_args.args[1]['message']=='This Substack post requires a subscription. Open the original post.'
