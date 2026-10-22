"""Interrupted local transcript replacement must leave the last source readable."""
from dataclasses import replace
import json
from unittest.mock import patch

import pytest

from api.db import TranscriptData


@pytest.mark.parametrize('existing', [False, True])
def test_failed_transcript_serialization_preserves_the_saved_source(db_interface, temp_data_dir, sample_transcript_data, existing):
    original = TranscriptData(**sample_transcript_data)
    path = temp_data_dir / 'transcripts' / (original.episode_id + '.json')
    if existing:
        assert db_interface.save_transcript(original)
    before = path.read_bytes() if existing else None
    def interrupted(payload, file, **kwargs):
        file.write('{"text":')
        raise OSError('Interrupted write')
    with patch('json.dump', side_effect=interrupted):
        with pytest.raises(OSError, match='Interrupted write'):
            db_interface.save_transcript(replace(original, text='New transcript'))
    if existing:
        assert path.read_bytes() == before
        assert db_interface.get_transcript(original.episode_id).text == original.text
    else:
        assert not path.exists()
    assert not list(path.parent.glob('*.tmp'))


def test_readers_see_the_old_source_until_the_new_file_is_complete(db_interface, temp_data_dir, sample_transcript_data):
    original = TranscriptData(**sample_transcript_data)
    assert db_interface.save_transcript(original)
    dump = json.dump
    seen = []
    def inspect(payload, file, **kwargs):
        dump(payload, file, **kwargs)
        seen.append(db_interface.get_transcript(original.episode_id).text)
    with patch('json.dump', side_effect=inspect):
        assert db_interface.save_transcript(replace(original, text='New complete transcript'))
    assert seen == [original.text]
    assert db_interface.get_transcript(original.episode_id).text == 'New complete transcript'


def test_failed_file_replacement_leaves_no_partial_or_temporary_source(db_interface, temp_data_dir, sample_transcript_data):
    original = TranscriptData(**sample_transcript_data)
    assert db_interface.save_transcript(original)
    with patch('pathlib.Path.replace', side_effect=OSError('Replacement unavailable')):
        with pytest.raises(OSError, match='Replacement unavailable'):
            db_interface.save_transcript(replace(original, text='New transcript'))
    assert db_interface.get_transcript(original.episode_id).text == original.text
    assert not list((temp_data_dir / 'transcripts').glob('*.tmp'))
