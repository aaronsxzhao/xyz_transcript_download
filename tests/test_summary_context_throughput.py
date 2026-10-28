import json
from unittest.mock import Mock

from focused_editor import _document_context, edit_whole_note
from reading_budget import PLAN, make_plan
from source_coverage import extraction_limit, split_source


def test_larger_english_segments_preserve_every_character_and_custom_limits():
    text=('This is the evidence and its essential condition.\n'*1200)
    chunks=split_source(text,extraction_limit(text))
    assert ''.join(chunks)==text
    assert all(len(part)<=12000 for part in chunks)
    assert len(chunks)<len(split_source(text,8000))
    assert extraction_limit(text,4000)==4000
    assert extraction_limit('中文原文'*5000)==8000


def test_global_context_is_bounded_and_never_claims_complete_source():
    rows=[{'id':str(i),'topic':'Topic '*30,'text':'This condition matters. '*200} for i in range(100)]
    context=_document_context(rows)
    assert not context['complete_source']
    assert len(json.dumps(context['entries'],ensure_ascii=False))<=12000


def test_editor_sees_later_answer_but_keeps_ownership_of_each_source_group():
    rows=[{'id':f'N{i}','topic':f'Topic {i}','text':'This source evidence matters. '*45} for i in range(12)]
    rows[-1]['text']='The later answer concerns polarization and belief-confirming reward. '+rows[-1]['text']
    call=Mock(return_value={});report={}
    token=PLAN.set(make_plan('English evidence '*20000,133*60,'en'))
    try:result=edit_whole_note(rows,call,report=report)
    finally:PLAN.reset(token)
    first=json.loads(call.call_args_list[0].args[1])
    assert 'polarization' in json.dumps(first['document_context'])
    assert 'N11' not in [n['id'] for g in first['groups'] for n in g['notes']]
    assert 'Only state that a' in call.call_args_list[0].args[0]
    assert [r['text'] for r in result]==[r['text'] for r in rows]
