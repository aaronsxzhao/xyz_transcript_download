"""Reader reviews retain independent valid items without inventing acceptance."""
import json
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from source_coverage import audit_source, source_units
from summary_errors import SummaryOutputError, strip_delivery_notices
from summarizer import Summarizer, Summary, KeyPoint
from note_summarizer import NoteSummarizer

SOURCE = 'A' * 800 + 'B' * 800 + 'C' * 800
FIELDS = {'body': 'A complete draft with all existing explanations.'}


def addition(id='added:1', unit='S1', text='Grounded extra detail.'):
    return {'id':id,'topic':'Chapter','heading':'Additional evidence','text':text,'source_ids':[unit]}


def receipt(unit='S1', target='body'):
    return {'unit':unit,'kind':'content','fields':[target]}


def review(data, source=SOURCE, fields=None):
    callback=Mock(return_value=data)
    value=audit_source(source,FIELDS if fields is None else fields,callback,repair=False,best_effort=True)
    callback.assert_called_once()
    return value


def test_missing_receipt_preserves_good_edits_additions_and_evidence():
    data={'edits':[{'field':'body','text':'Corrected detailed body.','source_ids':['S1']}],
          'additions':[addition()], 'coverage':[receipt('S1'),receipt('S2')]}
    original=deepcopy(data)
    result=review(data)
    assert result.fields['body']=='Corrected detailed body.'
    assert result.fields['added:1'].endswith('Grounded extra detail.')
    assert result.additions[0]['source_quote']=='A'*800
    assert result.unverified_units==['S3'] and not result.complete
    assert result.identified_gaps=={}
    assert data==original  # no accidental mutation of provider results


def test_bad_patch_affects_its_own_scope_and_keeps_siblings():
    data={'additions':[addition(),addition('added:2','S2',''),addition('added:3','S3','Third detail.')],
          'coverage':[receipt('S1'),receipt('S2'),receipt('S3')]}
    result=review(data)
    assert [row['id'] for row in result.additions]==['added:1','added:3']
    assert result.fields['body']==FIELDS['body']
    assert result.unverified_units==['S2']
    assert result.identified_gaps=={}


def test_unknown_source_patch_is_discarded_without_inventing_a_quote():
    result=review({'additions':[addition(unit='S99'),addition('added:2')],
                  'coverage':[receipt('S1'),receipt('S2'),receipt('S3')]})
    assert [row['id'] for row in result.additions]==['added:2']
    assert 'added:1' not in result.citations
    assert 'invalid_addition' in result.issues
    assert result.complete  # extra invalid metadata does not cancel real receipts


def test_unambiguous_packaging_repairs_do_not_invalidate_complete_review():
    data={'edits':None,'additions':{'text':'A real source detail.','source_ids':' s01 '},
          'coverage':[{'unit':' s01 ','kind':'content','fields':'body'},receipt('S2'),receipt('S3')]}
    result=review(data)
    assert result.complete
    assert result.additions[0]['id']=='added:1'
    assert result.additions[0]['heading']==result.additions[0]['topic']=='Additional details'
    assert result.additions[0]['source_quote']=='A'*800
    assert result.issues==[]


def test_unknown_metadata_cannot_create_a_receipt_for_an_unreviewed_real_unit():
    result=review({'coverage':[receipt('S1'),receipt('S99')]})
    assert result.unverified_units==['S2','S3'] and not result.complete
    assert result.identified_gaps=={}


def test_identical_duplicates_are_harmless_but_conflicting_receipts_remain_unverified():
    item=addition()
    data={'additions':[item,deepcopy(item)],'coverage':[receipt('S1'),receipt('S1'),receipt('S2'),receipt('S3')]}
    result=review(data)
    assert result.complete and len(result.additions)==1
    data['coverage'].append({'unit':'S2','kind':'non_content','reason':'greeting'})
    result=review(data)
    assert not result.complete and result.unverified_units==['S2']
    assert result.fields['added:1'].endswith(item['text'])


def test_conflicting_edits_do_not_erase_other_valid_additions():
    result=review({'edits':[{'field':'body','text':text,'source_ids':['S1']} for text in ['First correction.','Conflicting correction.']],
                  'additions':[addition('added:2','S2')], 'coverage':[receipt('S1'),receipt('S2'),receipt('S3')]})
    assert result.fields['body']=='First correction.'
    assert len(result.additions)==1 and not result.complete
    assert result.unresolved_fields==['body'] and result.unverified_units==['S1']


@pytest.mark.parametrize('bad',[None,17,'unexpected',[],{'kind':'non_content','reason':[],'unit':'S1'},
                                {'kind':'content','unit':{},'fields':['body']},
                                {'kind':'content','unit':'S1','fields':[{}]}])
def test_malformed_receipt_does_not_destroy_independent_valid_patch(bad):
    result=review({'additions':[addition()], 'coverage':[bad,receipt('S2'),receipt('S3')]})
    assert len(result.additions)==1
    assert 'A'*800 in result.citations['added:1']
    assert result.unverified_units==['S1']


@pytest.mark.parametrize('bad',[None,17,'bad',[],{'id':[],'source_ids':['S99'],'text':'Unverified'},
                                {'id':'added:9','source_ids':[['S1']],'text':'Unverified'}])
def test_malformed_addition_does_not_destroy_later_valid_items(bad):
    result=review({'additions':[bad,addition()], 'coverage':[receipt('S1'),receipt('S2'),receipt('S3')]})
    assert [row['id'] for row in result.additions]==['added:1']


def test_explicit_missing_content_is_distinct_from_missing_bookkeeping_and_keeps_order():
    result=review({'coverage':[{'unit':unit,'kind':'missing'} for unit in ['S3','S1']]})
    assert list(result.identified_gaps)==['S1','S3']
    assert result.identified_gaps['S1']=='A'*800
    assert result.unverified_units==['S1','S2','S3']
    assert 'S2' not in result.identified_gaps


def test_reader_mode_does_not_weaken_the_explicit_strict_contract():
    with pytest.raises(SummaryOutputError):
        audit_source(SOURCE,FIELDS,lambda *_:{'coverage':[receipt('S1')]},repair=False)


def podcast_draft():
    return Summary('episode','Title','Original overview',[
        KeyPoint('A','First generated detail.','Not an actual source quote','12:34'),
        KeyPoint('A','Second generated detail.','Actual source.','00:01:00')],['A'],['Keep this implication.'])


def test_one_missing_quote_does_not_discard_other_podcast_evidence_or_supplements():
    engine=Summarizer(api_key='fixture')
    data={'additions':[addition(text='A preserved source clarification.')],
          'coverage':[receipt(target='point:2')]}
    response=NS(choices=[NS(message=NS(content=json.dumps(data)))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response):
        result=engine._audit_summary(podcast_draft(),'[00:01:00] Actual source.')
    assert len(result.key_points)==3
    assert result.key_points[0].original_quote==result.key_points[0].timestamp==''
    assert result.key_points[1].original_quote=='Actual source.'
    assert result.key_points[1].timestamp=='00:01:00'
    assert result.key_points[2].summary.endswith('A preserved source clarification.')
    # The receipt covers the full source via point:2. A missing quotation in
    # another point is not an incomplete source review (the display contract
    # is also asserted in test_summary_display_regressions).
    assert 'coverage review did not complete' not in result.overview


def test_video_keeps_supplements_after_missing_coverage_and_never_calls_it_missing_content():
    engine=NoteSummarizer(api_key='fixture')
    with patch.object(engine,'_call_llm',return_value=json.dumps({'additions':[addition()], 'coverage':[receipt('S1')]})):
        text=engine._audit_note(SOURCE,'## Notes\nOriginal explanation.')
    assert 'Original explanation.' in text and 'Grounded extra detail.' in text
    assert 'coverage review did not complete' in text
    assert 'potentially uncovered content' not in text
    assert 'B'*800 not in text  # do not dump transcript merely for a broken receipt


def test_explicit_gap_includes_only_the_affected_original_source_passage():
    engine=NoteSummarizer(api_key='fixture')
    data={'coverage':[receipt('S1'),{'unit':'S2','kind':'missing'},receipt('S3')]}
    with patch.object(engine,'_call_llm',return_value=json.dumps(data)):
        text=engine._audit_note(SOURCE,'## Notes\nExisting detail.')
    assert 'potentially uncovered content' in text
    assert 'B'*800 in text and 'A'*800 not in text
    assert 'Existing detail.' in text


def test_empty_sections_and_duplicate_target_ids_are_repaired_without_a_warning():
    result=review({'edits':{},'additions':{},'coverage':[{'unit':unit,'kind':'content','fields':['body','body']} for unit in source_units(SOURCE)]})
    assert result.complete and result.issues==[]


def test_exact_ids_are_not_conflated_when_both_zero_padded_and_plain_ids_exist():
    result=review({'additions':[addition('added:1','S1','First detail.'),addition('added:01','S2','Separate detail.')],
                  'coverage':[receipt('S1','added:1'),receipt('S2','added:01'),receipt('S3')]})
    assert result.complete
    assert result.citations['added:1']=='A'*800
    assert result.citations['added:01']=='B'*800
    assert result.fields['added:1'].endswith('First detail.')
    assert result.fields['added:01'].endswith('Separate detail.')


def test_podcast_explicit_gap_preserves_original_evidence_and_takeaways():
    engine=Summarizer(api_key='fixture')
    data={'coverage':[{'unit':'S1','kind':'missing'}]}
    response=NS(choices=[NS(message=NS(content=json.dumps(data)))])
    with patch.object(engine,'_call_llm_with_retry',return_value=response):
        result=engine._audit_summary(podcast_draft(),'[00:01:00] Actual source.')
    assert result.takeaways==podcast_draft().takeaways
    assert result.key_points[-1].summary==result.key_points[-1].original_quote=='Actual source.'
    assert result.key_points[-1].timestamp=='00:01:00'
    assert 'potentially uncovered content' in result.overview


def test_generated_display_id_cannot_manufacture_a_model_coverage_link():
    item=addition()
    item.pop('id')
    result=review({'additions':[item], 'coverage':[receipt('S1','added:1'),receipt('S2'),receipt('S3')]})
    assert len(result.additions)==1
    assert result.additions[0]['source_quote']=='A'*800
    assert result.unverified_units==['S1'] and not result.complete
    assert 'invalid_note_reference' in result.issues
