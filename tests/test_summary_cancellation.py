"""Cancelling a paid summary must stop its request, not retry it."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from tenacity import wait_none
from api.routers.video_notes import VideoCancelledException


class Stream:
    def __init__(self):
        self.closed = False

    def __iter__(self):
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='partial'), finish_reason=None)])

    def close(self):
        self.closed = True


@pytest.mark.parametrize('video', [False, True])
def test_cancelled_stream_closes_and_does_not_start_more_provider_requests(video):
    from summarizer import Summarizer
    from note_summarizer import NoteSummarizer
    subject = (NoteSummarizer if video else Summarizer)(api_key='fixture', base_url='https://api.groq.com/openai/v1')
    streams = []
    def create(**kwargs):
        stream = Stream()
        streams.append(stream)
        return stream
    progress = Mock(side_effect=VideoCancelledException('Cancelled'))
    method = subject._call_llm if video else subject._call_llm_with_retry
    with patch.object(subject.client.chat.completions, 'create', side_effect=create) as request:
        with pytest.raises(VideoCancelledException):
            call = method.retry_with(wait=wait_none())
            if video:
                call(subject, 'system', 'user', progress)
            else:
                call(subject, 'user', progress)
    assert request.call_count == 1
    assert streams[0].closed


def test_podcast_cancellation_reaches_the_job_even_with_a_non_groq_provider():
    from summarizer import Summarizer
    subject = Summarizer(api_key='fixture', base_url='https://example.test/v1')
    with patch.object(subject, '_call_llm_with_retry', side_effect=VideoCancelledException('Cancelled')):
        with pytest.raises(VideoCancelledException):
            subject._summarize_single('episode', 'source', 'podcast', 'title')
