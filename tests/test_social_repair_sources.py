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


def test_repair_lists_storage_once_per_phase_and_reports_progress(monkeypatch):
 from api.routers import maintenance
 frames={f'repair_00-{i:02}.jpg':i for i in range(40)}
 existing=Mock(side_effect=[set(),set(frames)])
 monkeypatch.setattr(maintenance,'_frames',lambda *args:frames)
 monkeypatch.setattr(maintenance,'_existing',existing)
 reports=[]
 monkeypatch.setattr(maintenance,'_save_report',lambda key,value:reports.append(dict(value)))
 monkeypatch.setattr('cookie_manager.get_cookie_manager',lambda owner:Mock())
 monkeypatch.setattr('video_downloader.get_downloader',lambda *args:Mock(download_video=Mock(return_value='/tmp/video.mp4')))
 monkeypatch.setattr('screenshot_extractor.extract_screenshots_batch',Mock())
 monkeypatch.setattr('video_task_db.get_video_task_db',lambda:Mock(get_task=Mock(return_value={'status':'success','error':''})))
 maintenance._repair({'id':'repair','platform':'youtube','url':'https://youtube.com/watch?v=test'},'owner','key')
 assert existing.call_count==2
 assert any('Retrieving original' in r['message'] for r in reports)
 assert any('Rebuilding 40' in r['message'] for r in reports)
 assert reports[-1]['status']=='completed'


def test_status_storage_failure_does_not_abort_repair(monkeypatch):
 from api.routers import maintenance
 monkeypatch.setattr(maintenance,'USE_SUPABASE',True)
 client=Mock();client.storage.from_.return_value.upload.side_effect=RuntimeError('unavailable')
 monkeypatch.setattr(maintenance,'_client',lambda:client)
 monkeypatch.setattr(maintenance,'_reports',{})
 maintenance._save_report('fixture',{'status':'running','message':'Checking'})
 assert maintenance._reports['fixture']['message']=='Checking'


def test_running_status_includes_current_phase(monkeypatch):
 from api.routers import maintenance
 monkeypatch.setattr('video_task_db.get_video_task_db',lambda:Mock(get_task=Mock(return_value={'id':'note'})))
 key='media-repair/owner/note.json'
 monkeypatch.setattr(maintenance,'_running',{key})
 monkeypatch.setattr(maintenance,'_reports',{key:{'status':'running','message':'Rebuilding 12 screenshots…','missing':12}})
 assert maintenance.repair_status('note',Mock(id='owner'))['message']=='Rebuilding 12 screenshots…'
