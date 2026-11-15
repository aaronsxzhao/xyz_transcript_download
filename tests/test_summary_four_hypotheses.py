import copy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from coverage_ledger import _audit, efficient_audit
from transcript_reading import source_lines, validate_sections


def scene():
    _,lines=source_lines('Alpha needs the cold setting.\nBeta uses two passes.\nControl is stable.\n')
    spans=[{'start':lines[0].id,'end':lines[-1].id}]
    sections,_=validate_sections({'sections':[{'heading':'Control','paragraphs':[
        {'text':'Control is stable.','source_ranges':spans}]}]},lines)
    sections[0]['paragraphs'][0]['id']='P1'
    items=[{'id':'C1','kind':'condition','statement':'Alpha needs the cold setting.','source_ranges':spans},
           {'id':'C2','kind':'procedure','statement':'Beta uses two passes.','source_ranges':spans}]
    return lines,sections,items,spans


def receipt(ident,status='missing',grounded=True,pid=None):
    return {'item_id':ident,'status':status,'grounded':grounded,'duplicate':False,
            'support':[{'paragraph_id':pid}] if pid else []}


def local(items,rows):
    return {'failed_batches':0,'terminal_provider_failure':False,'requests':1,
            'corrected_inventory_items':[],'matching_rows':{r['item_id']:r for r in rows},
            'items':[{'id':item['id'],'kind':item['kind'],'source_ranges':item['source_ranges'],
                      'status':r['status'],'paragraph_ids':[s['paragraph_id'] for s in r['support']]}
                     for item,r in zip(items,rows)]}


@pytest.mark.parametrize('still_bad',[False,True])
def test_h1_grounding_concern_tracks_current_receipts_not_superseded_flags(still_bad):
    lines,sections,items,_=scene();owner=SimpleNamespace(quality_coverage_threshold=.9)
    def audit(engine,lines,sections,*args,inventory,verify_gaps=False,**kwargs):
        rows=[receipt(item['id'],'covered' if verify_gaps else 'partial',
                      grounded=not still_bad if verify_gaps else False,pid='P1') for item in inventory]
        return local(inventory,rows),inventory
    with patch('coverage_ledger._audit',side_effect=audit):
        report=efficient_audit(owner,lines,sections,
            prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},items),allow_repairs=False)
    assert report['grounding_concerns'] is still_bad


def test_h2_recovery_does_not_reuse_old_gap_receipts_after_an_earlier_batch_appends_prose():
    lines,sections,items,spans=scene();owner=SimpleNamespace(quality_coverage_threshold=.9);reused=[]
    def audit(engine,lines,current,*args,inventory,initial_rows=None,**kwargs):
        if initial_rows is None and len(current)==1:
            return local(inventory,[receipt(i['id']) for i in inventory]),inventory
        if inventory[0]['id']=='C1':
            current.append({'heading':'Both facts','paragraphs':[{'id':'NEW','text':'Both conditions are present.','source_ranges':spans}]})
        else:reused.append(initial_rows is not None)
        return local(inventory,[receipt(i['id'],'covered',pid='NEW') for i in inventory]),inventory
    with patch('coverage_ledger.ITEM_LIMIT',1),patch('coverage_ledger._audit',side_effect=audit):
        efficient_audit(owner,lines,sections,
            prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},items))
    assert reused==[False]


def test_h3_empty_repair_preserves_missing_and_does_not_rematch_unchanged_prose():
    lines,sections,items,_=scene();phases=[]
    def respond(engine,system,payload,validator):
        phases.append(payload['phase'])
        if payload['phase']=='match':return {'matches':[receipt(i['id']) for i in payload['items']]}
        if payload['phase']=='validate_inventory':return {'items':[{'id':i['id'],'supported':True} for i in payload['items']]}
        if payload['phase']=='repair':return {'sections':[]}
        raise AssertionError(payload['phase'])
    before=copy.deepcopy(sections)
    with patch('coverage_ledger.request',side_effect=respond):report,_=_audit(SimpleNamespace(),lines,sections,inventory=items)
    assert phases.count('match')==1
    assert sections==before and report['unresolved_items']==2


@pytest.mark.parametrize('verifier', ['separates_bad','all_bad','unavailable','still_regresses'])
def test_h4_independently_prune_bad_proposal_then_rematch_before_accepting_good_one(verifier):
    lines,sections,items,spans=scene();inventory=[{**items[0],'id':'C0','statement':'Control is stable.'},items[0]];phases=[]
    def respond(engine,system,payload,validator):
        phase=payload['phase'];phases.append(phase)
        if phase=='validate_inventory':return {'items':[{'id':i['id'],'supported':True} for i in payload['items']]}
        if phase=='repair':return {'sections':[{'heading':'Repair','paragraphs':[
            {'text':'Alpha needs the cold setting.','source_ranges':spans},
            {'text':'Control is unstable.','source_ranges':spans}]}]}
        if phase=='verify_repair_delta':
            if verifier=='unavailable':raise TimeoutError('synthetic')
            return {'paragraphs':[{'id':p['id'],'grounded':verifier!='all_bad' and p['text'].startswith('Alpha'),
                'adds_material_meaning':True,'contradicts_existing':p['text'].startswith('Control') or verifier=='all_bad'}
                for p in payload['proposed_paragraphs']]}
        if phase=='match':
            proposed={p['text']:p['id'] for p in payload['proposed_paragraphs']}
            good=proposed.get('Alpha needs the cold setting.');bad=proposed.get('Control is unstable.')
            regression=bool(bad) or bool(good and verifier=='still_regresses')
            return {'checked_proposed_paragraph_ids':payload['proposed_paragraph_ids'],'matches':[
                receipt('C0','contradicted' if regression else 'covered',pid=bad or 'P1'),
                receipt('C1','covered' if good else 'missing',pid=good)]}
        raise AssertionError(phase)
    with patch('coverage_ledger.request',side_effect=respond):report,_=_audit(SimpleNamespace(),lines,sections,inventory=inventory)
    kept=[p['text'] for s in sections[1:] for p in s['paragraphs']]
    if verifier=='separates_bad':
        assert kept==['Alpha needs the cold setting.']
        assert report['repairs_accepted']==1 and report['repairs_rejected']==1
        assert phases.count('match')==3
    else:
        assert kept==[] and report['status']=='unverified'
        if verifier=='unavailable':assert report['failed_batches']>0


def test_h1_failed_recovery_cannot_clear_unreplaced_grounding_receipt():
    lines,sections,items,_=scene();owner=SimpleNamespace(quality_coverage_threshold=.9)
    def audit(engine,lines,sections,*args,inventory,verify_gaps=False,**kwargs):
        report=local(inventory,[receipt(i['id'],'partial',False) for i in inventory])
        if verify_gaps:report.update(failed_batches=1,matching_rows={})
        return report,inventory
    with patch('coverage_ledger._audit',side_effect=audit):
        report=efficient_audit(owner,lines,sections,
            prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},items),allow_repairs=False)
    assert report['grounding_concerns'] and report['failed_batches']>0


def test_h2_unchanged_draft_can_still_reuse_valid_initial_gap_receipts():
    lines,sections,items,_=scene();owner=SimpleNamespace(quality_coverage_threshold=.9);recovery=[]
    def audit(engine,lines,current,*args,inventory,initial_rows=None,**kwargs):
        if initial_rows is not None:recovery.append(True)
        return local(inventory,[receipt(i['id']) for i in inventory]),inventory
    with patch('coverage_ledger.ITEM_LIMIT',1),patch('coverage_ledger._audit',side_effect=audit):
        efficient_audit(owner,lines,sections,
            prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},items))
    assert recovery==[True,True]


def test_h2_real_recovery_path_refreshes_gaps_and_avoids_a_second_unnecessary_repair():
    lines,sections,items,spans=scene();owner=SimpleNamespace(quality_coverage_threshold=.9);phases=[]
    text='Alpha needs the cold setting. Beta uses two passes.'
    def respond(engine,system,payload,validator):
        phase=payload['phase'];phases.append(phase)
        if phase=='validate_inventory':return {'items':[{'id':i['id'],'supported':True} for i in payload['items']]}
        if phase=='repair':return {'sections':[{'heading':'Both','paragraphs':[{'text':text,'source_ranges':spans}]}]}
        if phase=='match':
            existing=next((p['id'] for s in payload['global_draft'] for p in s['paragraphs'] if p['text']==text),None)
            return {'checked_proposed_paragraph_ids':payload['proposed_paragraph_ids'],
                    'matches':[receipt(i['id'],'covered' if existing else 'missing',pid=existing) for i in payload['items']]}
        raise AssertionError(phase)
    with patch('coverage_ledger.ITEM_LIMIT',1),patch('coverage_ledger.request',side_effect=respond):
        report=efficient_audit(owner,lines,sections,
            prepared_inventory=({'failed_batches':0,'inventory_failed_batches':0,'terminal_provider_failure':False},items))
    assert report['coverage_ratio']==1 and report['repairs_accepted']==1
    assert phases.count('repair')==1 and phases.count('validate_inventory')==1
    assert len(phases)==6


def test_full_failure_sampling_is_explicit_and_inside_existing_request_limit():
    import yaml
    from pathlib import Path
    from scripts.validate_authorized_episode import MAX_CALLS
    workflow=yaml.safe_load(Path('.github/workflows/review-saved-summary-samples.yml').read_text())
    inputs=workflow.get('on',workflow.get(True))['workflow_dispatch']['inputs']
    assert inputs['capture_final_diagnostics']['default'] is False
    assert MAX_CALLS==160
