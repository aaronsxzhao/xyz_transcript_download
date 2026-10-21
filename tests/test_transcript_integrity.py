from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
import pytest
from transcript_quality import validate_transcript, IncompleteTranscriptError


def test_reported_ten_second_transcript_is_rejected():
    with pytest.raises(IncompleteTranscriptError,match='incomplete'):
        validate_transcript(SimpleNamespace(duration=10,text='请不吝点赞 订阅 转发 打赏支持明镜与点点栏目'),5026)


def test_merged_duration_cannot_hide_empty_long_form_transcription():
    with pytest.raises(IncompleteTranscriptError,match='too little text'):
        validate_transcript(SimpleNamespace(duration=5026,text='Subscribe to this show'),5026)
    validate_transcript(SimpleNamespace(duration=5026,text='A substantive discussion. '*1000),5026)
    validate_transcript(SimpleNamespace(duration=10,text='A legitimate short clip.'),10)


def test_small_but_long_audio_is_split(tmp_path):
    from transcriber import APITranscriber
    audio=tmp_path/'long.mp3';audio.write_bytes(b'audio')
    transcriber=APITranscriber(api_key='synthetic',base_url='https://api.groq.com/openai/v1')
    with patch.object(transcriber,'_get_audio_duration',return_value=5026), \
         patch.object(transcriber,'_transcribe_file') as single, \
         patch.object(transcriber,'_transcribe_large_file',return_value='split'):
        assert transcriber.transcribe(audio,'episode')=='split'
        single.assert_not_called()


def test_download_restarts_when_cdn_ignores_range(tmp_path):
    from downloader import AudioDownloader
    audio=tmp_path/'clip.mp3';audio.write_bytes(b'partial')
    response=Mock(status_code=200,headers={'content-length':'10'})
    response.iter_content.return_value=[b'whole-file']
    session=Mock();session.get.return_value=response
    assert AudioDownloader()._download_with_resume(session,'https://example.com/audio',audio,10)
    assert audio.read_bytes()==b'whole-file'


def test_incomplete_result_does_not_replace_saved_transcript_or_summary(db_interface,create_test_podcast,create_test_episode,sample_summary_data):
    from api.db import SummaryData
    from api.routers import processing
    from api.schemas import ProcessingStatus
    from transcriber import Transcript
    create_test_podcast();create_test_episode()
    db_interface.save_summary(SummaryData(**sample_summary_data))
    job='bad-transcription'
    processing.jobs[job]=ProcessingStatus(job_id=job,user_id='local',status='pending')
    engine=Mock();engine.transcribe.return_value=Transcript('test-episode-456','zh',10,'Subscribe to our show',[])
    try:
        with patch.object(processing,'get_db',return_value=db_interface), \
             patch('api.user_settings.get_user_settings',return_value={}), \
             patch('downloader.get_downloader') as downloader, \
             patch('downloader.compress_audio',return_value=Path('/tmp/audio')), \
             patch('transcriber.get_transcriber',return_value=engine), \
             patch('summarizer.get_summarizer') as summarizer, \
             patch.object(processing,'notify_discord'):
            downloader.return_value.download.return_value=Path('/tmp/audio')
            processing.process_episode_sync(job,'local://test-episode-456',user_id='local',resummarize=True)
        assert processing.jobs[job].status=='failed'
        assert 'incomplete' in processing.jobs[job].message
        assert db_interface.get_transcript('test-episode-456') is None
        assert db_interface.get_summary('test-episode-456').overview==sample_summary_data['overview']
        summarizer.assert_not_called()
    finally: processing.jobs.pop(job,None)


def test_share_page_missing_duration_keeps_known_episode_duration(db_interface,create_test_podcast,create_test_episode):
    from api.routers import processing
    from api.schemas import ProcessingStatus
    from transcriber import Transcript
    create_test_podcast();create_test_episode()
    scraped=SimpleNamespace(eid='test-episode-456',pid='test-podcast-123',title='Test',duration=0,audio_url='https://example.com/audio',description='',pub_date='')
    job='missing-duration'
    processing.jobs[job]=ProcessingStatus(job_id=job,user_id='local',status='pending')
    engine=Mock();engine.transcribe.return_value=Transcript('test-episode-456','zh',10,'Subscribe to the show',[])
    try:
        with patch.object(processing,'get_db',return_value=db_interface), \
             patch('api.user_settings.get_user_settings',return_value={}), \
             patch('xyz_client.get_client') as xyz, \
             patch('downloader.get_downloader') as downloader, \
             patch('downloader.compress_audio',return_value=Path('/tmp/audio')), \
             patch('transcriber.get_transcriber',return_value=engine), \
             patch('summarizer.get_summarizer') as summarizer, \
             patch.object(processing,'notify_discord'):
            xyz.return_value.get_episode_by_share_url.return_value=scraped
            downloader.return_value.download.return_value=Path('/tmp/audio')
            processing.process_episode_sync(job,'https://www.xiaoyuzhoufm.com/episode/test-episode-456',user_id='local')
        assert scraped.duration==3600
        assert processing.jobs[job].status=='failed'
        assert 'incomplete' in processing.jobs[job].message
        assert db_interface.get_transcript('test-episode-456') is None
        summarizer.assert_not_called()
    finally: processing.jobs.pop(job,None)


@pytest.mark.parametrize('media,expected', [({'source':{'url':'https://example.com/full.mp3'}},'https://example.com/full.mp3'),(None,'https://example.com/preview.mp3')])
def test_share_page_prefers_full_recording_but_tolerates_missing_structured_media(media,expected):
    import json
    from xyz_client import XyzClient
    client=XyzClient.__new__(XyzClient)
    response=Mock()
    data={'props':{'pageProps':{'episode':{'pid':'show','duration':5026,'media':media}}}}
    response.content=('<meta property="og:audio" content="https://example.com/preview.mp3"><script type="application/json">'+json.dumps(data)+'</script>').encode()
    client.session=Mock();client.session.get.return_value=response
    episode=client.get_episode_by_share_url('https://www.xiaoyuzhoufm.com/episode/example')
    assert episode.audio_url==expected
    assert episode.duration==5026
