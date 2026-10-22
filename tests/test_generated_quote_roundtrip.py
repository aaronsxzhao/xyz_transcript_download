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
    s = Summarizer(api_key='fixture')
    def draft(text):
        return {'overview': 'Overview', 'topics': ['Original chapter'], 'takeaways': [],
                'key_points': [{'topic': 'Original chapter', 'summary': '#### Detail\n\n' + text,
                                'original_quote': text, 'timestamp': '00:00:00'}]}
    audit = {'coverage': [{'unit': 'S1', 'kind': 'content', 'fields': ['point:1']}]}
    if chunked:
        s.chunk_chars = 65
        assert len(split_source(s._transcript_text(transcript), s.chunk_chars)) == 2
        answers = [draft(first), audit, draft(second), audit, {'overview': 'Full overview', 'takeaways': []}]
        expected = [(first, '00:00:00'), (second, '00:00:31')]
    else:
        answers = [draft(first), {'coverage': [{'unit': 'S1', 'kind': 'content', 'fields': ['point:1', 'point:2']}]}]
        answers[0]['key_points'].extend(draft(second)['key_points'])
        expected = [(first, '00:00:00'), (second, '00:00:31')]
    # Only the provider response is mocked: extraction, coverage validation,
    # chunk assembly, persistence, API serialization and exports run normally.
    with patch.object(s, '_call_llm_with_retry', side_effect=[response(data) for data in answers]) as provider:
        note = s.summarize(transcript, episode_title='New note')
    assert provider.call_count == len(answers)
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
