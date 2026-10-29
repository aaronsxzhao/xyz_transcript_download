import json
from unittest.mock import Mock

import pytest

from bilibili_parts import find_task, part_manifest, prepare_parts, selected_part
from video_downloader import BilibiliDownloader, VideoDownloadError, normalize_video_url

BASE = 'https://www.bilibili.com/video/BV1zZrCBoEie'


def manifest():
    return part_manifest({'title':'Collection', 'videos':3, 'pages':[
        {'page':i, 'cid':100+i, 'duration':i*60, 'part':f'Chapter {i}'} for i in range(1,4)]}, BASE)


@pytest.mark.parametrize('page', [1,2,30])
def test_explicit_selection_survives_normalization_and_timestamp_links(page):
    from screenshot_extractor import replace_content_markers
    url = normalize_video_url(f'{BASE}?p={page}&share_source=copy', 'bilibili')
    assert url == f'{BASE}?p={page}'
    assert f'?t=15&p={page}' in replace_content_markers('*Content-[00:15]', url, 'bilibili')
    assert selected_part(BASE) is None


@pytest.mark.parametrize('query', ['p=0','p=-1','p=no','p=','p=1&p=2'])
def test_invalid_selection_cannot_silently_become_collection(query):
    with pytest.raises(ValueError):
        normalize_video_url(BASE+'?'+query,'bilibili')


def test_incomplete_manifest_is_not_first_part_success():
    with pytest.raises(ValueError):
        part_manifest({'videos':2,'pages':[{'page':1,'cid':1,'duration':60}]},BASE)
    downloader = BilibiliDownloader()
    downloader.get_metadata = Mock(return_value=None)
    with pytest.raises(VideoDownloadError,match='complete Bilibili part list'):
        downloader.resolve_parts(BASE)


def test_api_manifest_uses_part_duration_and_title(monkeypatch):
    data={'title':'Collection','videos':3,'pages':[
        {'page':i,'cid':100+i,'duration':i*60,'part':f'Chapter {i}'} for i in range(1,4)]}
    monkeypatch.setattr('requests.get',Mock(return_value=Mock(json=lambda:{'code':0,'data':data})))
    d=BilibiliDownloader()
    assert len(d.resolve_parts(BASE))==3
    assert d.get_metadata(BASE+'?p=2').duration==120
    assert 'P1/3' in d.get_metadata(BASE+'?p=1').title


@pytest.fixture
def tasks(tmp_path):
    from video_task_db import VideoTaskDB
    db = VideoTaskDB(tmp_path/'parts.db')
    ident = db.create_task({'url':BASE,'user_id':'owner','platform':'bilibili'})
    return db, db.get_task(ident,'owner')


def test_collection_retry_repairs_admission_without_duplicate_rows(tasks):
    db, root = tasks
    options = {'formats':['summary','screenshot'],'model':'chosen','quality':'fast'}
    submit = Mock(side_effect=RuntimeError('queue interrupted'))
    with pytest.raises(RuntimeError):
        prepare_parts(db,root,manifest(),BASE,options,submit)
    orphan = db.get_task_by_url(BASE+'?p=2','owner')
    assert orphan and orphan['model']=='chosen'
    accepted = Mock()
    part = prepare_parts(db,root,manifest(),BASE,options,accepted)
    assert part['page']==1 and part['duration']==60
    assert accepted.call_args_list[0].args==(orphan['id'],BASE+'?p=2')
    db.update_task(orphan['id'],{'status':'success','markdown':'Saved P2',
        'transcript_json':json.dumps({'text':'Verified P2','bilibili_part':manifest()[1]})})
    accepted.reset_mock()
    prepare_parts(db,root,manifest(),BASE,options,accepted)
    assert accepted.call_count==1 and accepted.call_args.args[1].endswith('?p=3')
    stored=db.get_task(root['id'],'owner')
    assert len(stored['source_metadata']['bilibili_parts'])==3
    assert stored['duration']==60 and 'P1/3' in stored['title']
    assert find_task(db,BASE+'?p=1','owner')['id']==root['id']
    assert find_task(db,BASE+'?p=1','other') is None


def test_explicit_part_does_not_enqueue_siblings(tasks):
    db,root=tasks
    submit=Mock()
    part=prepare_parts(db,root,manifest(),BASE+'?p=2',{},submit)
    assert part['page']==2 and part['duration']==120
    submit.assert_not_called()
    with pytest.raises(ValueError,match='does not exist'):
        prepare_parts(db,root,manifest(),BASE+'?p=4',{},submit)


def test_media_cache_identity_distinguishes_parts_and_old_unscoped_files(monkeypatch):
    from video_downloader import YtdlpDownloader
    audio=Mock();video=Mock();subs=Mock()
    monkeypatch.setattr(YtdlpDownloader,'download_audio',audio)
    monkeypatch.setattr(YtdlpDownloader,'download_video',video)
    monkeypatch.setattr(YtdlpDownloader,'get_subtitles',subs)
    d=BilibiliDownloader()
    for page in [1,2]:
        url=BASE+f'?p={page}'
        d.download_audio(url,'task');d.download_video(url,'task');d.get_subtitles(url,'task')
    for method in [audio,video,subs]:
        assert [call.args[1] for call in method.call_args_list]==['task-bp1','task-bp2']


@pytest.mark.parametrize("selected", [None, 2])
def test_worker_does_not_reuse_unscoped_transcript_and_saves_part_provenance(tasks,monkeypatch,selected):
    from api.routers import video_notes as routes
    from video_downloader import VideoMetadata
    db,root=tasks
    db.update_task(root['id'],{'transcript_json':json.dumps({'text':'Old unverified source '*10,'segments':[]}),
                              'thumbnail':'https://i0.hdslb.com/cover'})
    monkeypatch.setattr('video_task_db.get_video_task_db',lambda:db)
    monkeypatch.setattr(routes,'_broadcast_from_thread',Mock())
    monkeypatch.setattr(routes,'start_task',Mock())
    monkeypatch.setattr('api.user_settings.get_user_settings',lambda owner:{})
    monkeypatch.setattr('api.llm_settings.resolve_llm_settings',lambda *args:{'model':'test','api_key':'test','base_url':'https://example.test'})
    monkeypatch.setattr('cookie_manager.get_cookie_manager',lambda owner:Mock(get_cookie=Mock(return_value='fixture')))
    part=manifest()[(selected or 1)-1]
    store=Mock();store.latest.return_value=None
    monkeypatch.setattr('execution_store.enabled',lambda:True)
    monkeypatch.setattr('execution_store.get_store',lambda:store)
    d=Mock()
    d.resolve_parts.return_value=manifest()
    d.get_metadata.return_value=VideoMetadata(title=part['title'],duration=part['duration'])
    d.get_subtitles.return_value=[{'start':0,'end':part['duration'],'text':'Correct selected part source '*10}]
    monkeypatch.setattr('video_downloader.get_downloader',lambda *a:d)
    summarizer=Mock(generate_note=Mock(return_value='## Result\n\n*Content-[00:15]'))
    monkeypatch.setattr('note_summarizer.get_note_summarizer',lambda **k:summarizer)
    args=(root['id'],BASE+(f'?p={selected}' if selected else ''),'bilibili','detailed',['summary','link'],'medium','','',False,4,3,3,'owner')
    routes.process_video_note_sync(*args)
    saved=db.get_task(root['id'],'owner')
    assert saved['status']=='success',saved['message']
    assert saved['transcript']['bilibili_part']['page']==(selected or 1)
    assert saved['duration']==part['duration']
    assert store.enqueue.call_count==(2 if selected is None else 0)
    if selected is None:
        assert [call.args[4]['url'] for call in store.enqueue.call_args_list]==[BASE+'?p=2',BASE+'?p=3']
        assert all(call.args[0]=='owner' for call in store.enqueue.call_args_list)
    assert 'Correct selected part' in summarizer.generate_note.call_args.kwargs['transcript_text']
    assert f'?t=15&p={selected or 1}' in saved['markdown']
    d.get_subtitles.reset_mock()
    routes.process_video_note_sync(*args)
    d.get_subtitles.assert_not_called()
