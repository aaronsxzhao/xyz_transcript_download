import json
from unittest.mock import Mock

import pytest

from reading_repetition import remove_repeated_examples, repetition_candidates
from source_coverage import audit_source
from summary_errors import ProcessingCancelledError


CLAIM = 'The laboratory experiment found that participants repeatedly selected unpleasant stimulation, suggesting that reward circuits can reinforce aversive emotional states.'
LIMIT = 'The later discussion adds that individual regulation cannot replace institutional changes or public accountability.'


def sections():
    return [dict(text='## Mechanism\n\n'+CLAIM+'\n\n> Original quotation.\n', ids=['A']),
            dict(text='## Limits\n\n'+LIMIT+' '+CLAIM+'\n\nScreenshot-[02:00]\n', ids=['B'])]


def approve(system, payload, timeout):
    assert timeout == 60
    return {'checks':[dict(id=c['id'], same_information=True, no_unique_qualification=True,
                           safe_to_remove=True) for c in json.loads(payload)['candidates']]}


def test_duplicate_example_removed_but_unique_limit_quote_and_media_unchanged():
    rows=sections();before=json.dumps(rows);call=Mock(side_effect=approve)
    output,report=remove_repeated_examples(rows,call)
    assert json.dumps(rows)==before
    assert output[0]==rows[0] and CLAIM not in output[1]['text']
    assert LIMIT in output[1]['text'] and 'Screenshot-[02:00]' in output[1]['text']
    assert output[1]['ids']==['B'] and report['removed']==1 and call.call_count==1


@pytest.mark.parametrize('response', [{}, {'checks':[{'id':'R1','same_information':True}]},
    {'checks':[dict(id='R1',same_information=True,no_unique_qualification=False,safe_to_remove=True)]},
    {'checks':[dict(id='R1',same_information=True,no_unique_qualification=True,safe_to_remove=True)]*2}])
def test_uncertain_or_ambiguous_review_never_deletes(response):
    rows=sections()
    assert remove_repeated_examples(rows,Mock(return_value=response))[0]==rows


def test_timeout_retains_reading_but_cancellation_propagates():
    rows=sections()
    assert remove_repeated_examples(rows,Mock(side_effect=TimeoutError()))[0]==rows
    with pytest.raises(ProcessingCancelledError):
        remove_repeated_examples(rows,Mock(side_effect=ProcessingCancelledError()))


def test_quotes_code_and_changed_numbers_not_duplicate_candidates():
    rows=sections()
    rows[1]['text']='> '+CLAIM+'\n\n```\n'+CLAIM+'\n```'
    assert not repetition_candidates(rows)
    rows=[{'text':CLAIM+' The sample involved 100 adults.'},
          {'text':CLAIM.replace('participants','200 participants')}]
    assert not repetition_candidates(rows)


def test_last_substantive_sentence_not_removed_leaving_empty_section():
    rows=sections();rows[1]['text']='## Heading\n\n'+CLAIM+'\n\nScreenshot-[02:00]'
    assert remove_repeated_examples(rows,approve)[0]==rows


def test_chinese_sentences_without_spaces_keep_new_qualification():
    claim='实验观察发现，参与者反复选择伴随轻微愤怒与挫折感的刺激，讲述者认为这说明奖赏机制不一定只强化令人愉快的感受，也可能让不愉快的情绪状态反复出现，但并没有把这种解释视为已经普遍证实的结论。'
    condition='后文进一步强调，个人情绪调节不能替代公共机构承担责任以及信息平台进行制度层面的改变。'
    rows=[{'text':claim},{'text':claim+condition}]
    result,report=remove_repeated_examples(rows,approve)
    assert report['removed']==1 and result[1]['text']==condition


def test_invalid_exclusion_rechecked_as_content_without_rewriting():
    fields={'body':'Repeated experiments suggest a conditional mechanism.'}
    first={'coverage':[{'unit':'S1','kind':'non_content','reason':'repetition'}]}
    def retry(system,payload,timeout):
        assert timeout==60 and json.loads(payload)['draft_fields']==fields
        return {'coverage':[{'unit':'S1','kind':'content','fields':['body']}],
                'edits':[{'field':'body','text':'Invented','source_ids':['S1']}]}
    review=audit_source('The speaker repeats the conditional mechanism.',fields,Mock(return_value=first),
                        best_effort=True,recheck=retry)
    assert review.complete and review.fields==fields
    assert review.receipt_recheck=={'attempted':1,'resolved':1}


@pytest.mark.parametrize('response', [{}, {'coverage':[{'unit':'S1','kind':'non_content','reason':'repetition'}]},
    {'coverage':[{'unit':'S1','kind':'content','fields':['absent']}]},
    {'coverage':[{'unit':'S1','kind':'missing'}]}])
def test_failed_recheck_does_not_manufacture_coverage(response):
    first={'coverage':[{'unit':'S1','kind':'non_content','reason':'repetition'}]}
    review=audit_source('Important argument.',{'body':'Draft'},Mock(return_value=first),
                        best_effort=True,recheck=Mock(return_value=response))
    assert not review.complete and review.unverified_units==['S1']
    assert review.receipt_recheck['resolved']==0


def test_valid_receipt_needs_no_additional_call():
    retry=Mock()
    review=audit_source('Important argument.',{'body':'Draft'},
        Mock(return_value={'coverage':[{'unit':'S1','kind':'content','fields':['body']}]}),
        best_effort=True,recheck=retry)
    assert review.complete
    retry.assert_not_called()
