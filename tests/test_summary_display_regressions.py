from unittest.mock import patch
from note_presentation import deduplicate_adjacent_headings
from source_coverage import audit_source, SourceReview
from summarizer import Summarizer, Summary, KeyPoint


def test_only_adjacent_top_level_identical_headings_are_deduplicated():
    text = '#### Claim\n\n#### Claim\n\nBody\n\n#### Claim\n\nOther body\n\n```md\n#### A\n#### A\n```\n\n> #### B\n> #### B\n'
    result = deduplicate_adjacent_headings(text)
    assert result.count('#### Claim') == 2
    assert '#### A\n#### A' in result
    assert '> #### B\n> #### B' in result


def test_noncontent_requires_all_units_to_be_verified():
    result = audit_source('Thanks for listening.', {'point:1':'Closing remarks'}, lambda *args: {
        'edits': [], 'additions': [], 'coverage': [{'unit':'S1','kind':'non_content','reason':'greeting'}]
    }, best_effort=True)
    assert result.complete and result.non_content_only
    missing = audit_source('Thanks for listening.', {'point:1':'Closing remarks'}, lambda *args: {
        'edits': [], 'additions': [], 'coverage': []
    }, best_effort=True)
    assert not missing.non_content_only


def test_verified_empty_outro_does_not_disable_whole_document_editor():
    engine = Summarizer.__new__(Summarizer)
    empty = Summary('e','title','Only a closing advertisement.',[],[],[])
    review = SourceReview({'overview': empty.overview}, [], {}, non_content_only=True)
    with patch('summarizer.audit_source', return_value=review):
        result = engine._audit_summary(empty, 'Please support the show.')
    assert not result.overview and not result.key_points


def test_missing_quote_does_not_mislabel_complete_source_review():
    engine = Summarizer.__new__(Summarizer)
    summary = Summary('e','title','Overview',[KeyPoint('Topic','A supported point','invented quote','')],['Topic'],[])
    review = SourceReview({'overview':'Overview','point:1':'A supported point'}, [], {})
    with patch('summarizer.audit_source', return_value=review):
        result = engine._audit_summary(summary, 'Source supports this claim.')
    assert result.overview == 'Overview'
    assert result.key_points[0].original_quote == ''


def test_out_of_range_screenshot_does_not_reuse_or_relabel_cached_last_frame(tmp_path):
    from screenshot_extractor import extract_screenshot
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'video')
    (tmp_path / 'task_02-00.jpg').write_bytes(b'old wrong frame')
    with patch('screenshot_extractor.SCREENSHOTS_DIR',tmp_path), patch('screenshot_extractor.run_media_process') as process:
        assert extract_screenshot(str(video),120,'task',duration=60) is None
        process.assert_not_called()


def test_source_review_cannot_silently_delete_video_frames():
    original = 'Original claim.\n\nScreenshot-[01:00]\n\nLater claim.\n\nScreenshot-[02:00]'
    response = {'edits':[{'field':'body','text':'Corrected claim.','source_ids':['S1']}],
                'additions':[], 'coverage':[{'unit':'S1','kind':'content','fields':['body']}]}
    review = audit_source('Source claim.', {'body':original}, lambda *args:response, best_effort=True)
    assert review.fields['body'] == original
    assert 'source_media' in review.issues and not review.complete
    response['edits'][0]['text'] = original.replace('Original claim.', 'Corrected claim.')
    valid = audit_source('Source claim.', {'body':original}, lambda *args:response, best_effort=True)
    assert valid.complete and 'Corrected claim.' in valid.fields['body']
