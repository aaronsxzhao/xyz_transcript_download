from unittest.mock import Mock,patch
from pathlib import Path
import pytest
from api.db import TranscriptData,SummaryData
from api.schemas import ProcessingStatus


@pytest.mark.asyncio
async def test_paid_source_is_explained_in_episode_lists_and_invalid_summary(client,db_interface,create_test_podcast,create_test_episode,sample_transcript_data,sample_summary_data):
    create_test_podcast();create_test_episode()
    db_interface.set_episode_source_status('test-episode-456','purchase_required')
    db_interface.save_transcript(TranscriptData(**{**sample_transcript_data,'duration':10,'text':'Subscribe to this show'}))
    db_interface.save_summary(SummaryData(**{**sample_summary_data,'key_points':[],'topics':[]}))
    for path in ['/api/episodes/test-episode-456','/api/podcasts/test-podcast-123/episodes','/api/podcasts/content?pid=test-podcast-123']:
        response=await client.get(path)
        assert response.status_code==200
        row=response.json()[0] if isinstance(response.json(),list) else response.json()
        assert row['source_status']=='purchase_required'
        assert 'Purchase required' in row['source_message']
    response=await client.get('/api/summaries/test-episode-456')
    assert response.status_code==200
    assert 'incomplete transcript' in response.json()['quality_warning']
    assert response.json()['source_status']=='purchase_required'
    assert (await client.get('/api/summaries/test-episode-456/html')).status_code==409


def test_known_restricted_source_never_reaches_download_or_llm(db_interface,create_test_podcast,create_test_episode):
    from api.routers import processing
    create_test_podcast();create_test_episode()
    db_interface.set_episode_source_status('test-episode-456','purchase_required')
    job='paid-source'
    processing.jobs[job]=ProcessingStatus(job_id=job,user_id='local',status='pending')
    try:
        with patch.object(processing,'get_db',return_value=db_interface),patch('api.user_settings.get_user_settings',return_value={}), \
             patch('downloader.get_downloader') as downloader,patch('transcriber.get_transcriber') as transcriber, \
             patch('summarizer.get_summarizer') as summarizer:
            processing.process_episode_sync(job,'local://test-episode-456',user_id='local')
        assert processing.jobs[job].status=='failed'
        assert 'Purchase required' in processing.jobs[job].message
        downloader.assert_not_called();transcriber.assert_not_called();summarizer.assert_not_called()
    finally: processing.jobs.pop(job,None)


def test_incomplete_download_reports_source_problem_without_retrying_same_placeholder(tmp_path):
    from downloader import AudioDownloader
    from types import SimpleNamespace
    engine=AudioDownloader(tmp_path)
    engine._download_with_resume=Mock(return_value=True)
    episode=SimpleNamespace(eid='example',pid='show',audio_url='https://example.com/audio.mp3',title='Episode',duration=5026)
    path=engine.get_audio_path(episode);path.write_bytes(b'placeholder')
    with patch.object(engine,'is_downloaded',return_value=False),patch('downloader._get_audio_duration_ffprobe',return_value=10),patch('downloader.create_session_with_retries'):
        assert engine.download(episode) is None
    assert 'only 10s' in engine.last_error
    assert 'purchase/sign-in' in engine.last_error
    engine._download_with_resume.assert_called_once()


@pytest.mark.asyncio
async def test_empty_long_summary_has_consistent_quality_and_is_not_recommended(client,db_interface,create_test_podcast,create_test_episode,sample_transcript_data,sample_summary_data):
    create_test_podcast();create_test_episode()
    db_interface.save_transcript(TranscriptData(**{**sample_transcript_data,'text':'Full substantive transcript. '*100}))
    db_interface.save_summary(SummaryData(**{**sample_summary_data,'key_points':[],'topics':[]}))
    summary=(await client.get('/api/summaries/test-episode-456')).json()
    assert 'no topics or key points' in summary['quality_warning']
    for path in ['/api/episodes/test-episode-456','/api/podcasts/content?pid=test-podcast-123']:
        row=(await client.get(path)).json()
        if isinstance(row,list): row=row[0]
        assert row['has_summary'] is True
        assert row['quality_status']=='needs_review'
    assert (await client.get('/api/library')).json()['items']==[]
    assert (await client.get('/api/summaries/recent')).json()==[]
    for format in ['html','markdown']:
        assert (await client.get('/api/summaries/test-episode-456/'+format)).status_code==409
    # Historic data remains available for inspection/recovery.
    assert db_interface.get_summary('test-episode-456') is not None
