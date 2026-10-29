"""New short and chunked notes keep their source evidence through storage/API/export."""
from dataclasses import asdict
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

import pytest

from api.db import SummaryData, get_db
from source_coverage import split_source
from summarizer import Summarizer
from transcriber import Transcript, TranscriptSegment


def response(data):
    return NS(choices=[NS(message=NS(content=json.dumps(data)))])


@pytest.mark.asyncio
@pytest.mark.parametrize('chunked', [False, True])
async def test_new_generation_retains_quotes_through_save_read_and_export(client, chunked):
    first = 'A conditional forecast, not a fact.'
    second = 'The independent closing example survives.'
    transcript = Transcript('new-evidence', 'en', 62, first + ' ' + second,
                            [TranscriptSegment(0, 20, first), TranscriptSegment(31, 60, second)])
    s=Summarizer(api_key='fixture',generation_mode='segmented' if chunked else 'single')
    s.chunk_chars=1000
    from tests.test_transcript_reading import provider, section
    from source_coverage import spoken_source
    calls=[]
    def response(owner,system,payload,timeout):
        data=json.loads(payload)
        result=provider(calls)(owner,system,payload,timeout)
        if 'mode' in data:
            result['sections']=[section([row],spoken_source(row['text']).strip()) for row in data['primary_source']]
        return result
    # Mock only provider output: source association, persistence, APIs and exports
    # run through their real code in both explicit generation modes.
    with patch('transcript_reading.call_json',side_effect=response):
        note=s.summarize(transcript,episode_title='New note')
    expected=[(first,'00:00:00'),(second,'00:00:31')]
    assert note is not None
    assert get_db().save_summary(SummaryData(**asdict(note)))
    loaded = await client.get('/api/summaries/new-evidence')
    assert loaded.status_code == 200
    assert [(p['original_quote'], p['timestamp']) for p in loaded.json()['key_points']] == expected
    markdown = await client.get('/api/summaries/new-evidence/markdown')
    html = await client.get('/api/summaries/new-evidence/html')
    assert markdown.status_code == html.status_code == 200
    for quote, timestamp in expected:
        assert '> ' + quote in markdown.json()['markdown']
        assert quote in html.text and timestamp in html.text
