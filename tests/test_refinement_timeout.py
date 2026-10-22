"""A timed-out refinement must return without waiting or saving late results."""
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from api.routers import processing


def test_refinement_timeout_does_not_wait_for_or_publish_the_late_worker(monkeypatch):
    release, entered, returned = threading.Event(), threading.Event(), threading.Event()
    transcriber, summarizer, db = Mock(), Mock(), Mock()
    def blocked(*args):
        entered.set()
        release.wait(3)
        return NS(episode_id='episode', language='en', duration=10, text='Original evidence.', segments=[])
    transcriber.transcribe.side_effect = blocked
    monkeypatch.setattr(processing, 'BACKGROUND_REFINEMENT_TIMEOUT', .01)
    def run():
        try: processing._background_refinement('audio', NS(eid='episode', title='Episode', duration=10), NS(topics=[]), db, transcriber, summarizer, 'owner')
        finally: returned.set()
    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert entered.wait(1)
        assert returned.wait(.4), 'Timeout still waits for the transcription worker'
    finally:
        release.set()
        thread.join(2)
    db.save_transcript.assert_not_called()
    db.save_summary.assert_not_called()
    summarizer.summarize.assert_not_called()


@pytest.mark.parametrize('source_saved', [True, False])
def test_refinement_saves_quotes_only_after_the_source_is_saved(monkeypatch, source_saved):
    from summarizer import Summary, KeyPoint
    from transcriber import Transcript
    transcriber, summarizer, db = Mock(), Mock(), Mock()
    transcriber.transcribe.return_value = Transcript('episode', 'en', 10, 'Original evidence.', [])
    note = Summary('episode', 'Episode', 'Overview', [KeyPoint('Topic', 'Detail', 'Original evidence.', '')], ['Topic'], [])
    summarizer.summarize.return_value = note
    db.save_summary.return_value = True
    db.save_transcript.return_value = source_saved
    monkeypatch.setattr(processing, 'BACKGROUND_REFINEMENT_TIMEOUT', 1)
    processing._background_refinement('audio', NS(eid='episode', title='Episode', duration=10), note, db, transcriber, summarizer, 'owner')
    db.save_transcript.assert_called_once()
    if source_saved:
        assert db.save_summary.call_args.args[0].key_points[0]['original_quote'] == 'Original evidence.'
    else:
        db.save_summary.assert_not_called()
