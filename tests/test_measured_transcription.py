from types import SimpleNamespace
from unittest.mock import patch
import threading
from transcriber import APITranscriber, Transcript
from reading_progress import MeasuredProgress


def test_api_waiting_does_not_simulate_work(tmp_path):
    audio=tmp_path/'audio.wav';audio.write_bytes(b'fixture')
    engine=APITranscriber(api_key='fixture')
    release=threading.Event();observed=[]
    response=SimpleNamespace(text='This is the spoken source. '*12,language='en',duration=5,segments=[])
    def provider(**kwargs):
        assert release.wait(3)
        return response
    def progress(value):
        observed.append(value)
        if len(observed)>=3:release.set()
    try:
        with patch.object(engine,'_wait_for_rate_limit'),patch.object(engine,'_get_audio_duration',return_value=5),patch.object(engine.client.audio.transcriptions,'create',side_effect=provider):
            assert engine.transcribe(audio,'e',progress_callback=progress)
        assert observed[:3]==[0,0,0]
        assert observed[-1]==1
    finally:release.set()


def test_chunks_advance_only_after_results_and_report_counts(tmp_path):
    audio=tmp_path/'audio.mp3';audio.write_bytes(b'audio')
    engine=APITranscriber.__new__(APITranscriber);engine.max_size=10;engine.last_error=''
    engine._get_audio_duration=lambda path:1200 if path==audio else 600
    def extract(source,target,start,duration,cancel_check):target.write_bytes(b'chunk');return True
    engine._extract_chunk=extract
    def transcribe(path,eid,language,callback):
        callback(0);callback(.9)  # Parsing a response isn't a completed segment yet.
        return Transcript(eid,'en',600,'source',[])
    engine._transcribe_file=transcribe
    values=[]
    assert engine._transcribe_large_file(audio,'e','',values.append)
    measured=[v for v in values if isinstance(v,MeasuredProgress)]
    assert all(v in (0,.5,1) for v in measured)
    assert any(v.completed==1 and v.total==2 for v in measured)
    assert values[-1]==1
