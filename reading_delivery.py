"""Delivery contract: 90% material coverage, no known unsupported prose.

Model review is evidence, not a guarantee of factual truth. Unaccepted candidates
remain checkpointed internal work and must not be published as finished notes.
"""
import copy
import json

from processing_execution import fingerprint
from summary_errors import SummaryOutputError, is_cancellation


def draft_identity(sections, overview):
    return fingerprint({'overview':overview, 'paragraphs':sorted([
        {key:p.get(key) for key in ('id','text','source_ranges','raw')}
        for s in sections for p in s['paragraphs']], key=lambda p:p['id'])})


def repair_unsupported(engine, lines, sections, ids):
    """Replace only rejected paragraphs; preserve their IDs and source scope."""
    from transcript_reading import serialize, validate_sections
    from reading_editor import call_editor
    from reading_language import source_language_lock
    paragraphs = {p['id']:p for s in sections for p in s['paragraphs'] if p['id'] in ids}
    if not paragraphs: return
    payload = {'phase':'repair_grounding', 'paragraphs':[
        {'id':ident, 'rejected_text':p['text'], 'original_source':serialize([lines[i] for i in p['indices']])}
        for ident,p in paragraphs.items()]}
    payload['review_attempt'] = getattr(engine, '_quality_attempt', 0)
    def validate(data):
        rows = data.get('replacements') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)!=len(paragraphs): raise ValueError('Incomplete replacements')
        found = {}
        for row in rows:
            ident = row.get('id') if isinstance(row,dict) else None
            if ident not in paragraphs or ident in found: raise ValueError('Invalid replacement identity')
            parsed, _ = validate_sections({'sections':[{'heading':'Correction','paragraphs':[row]}]}, lines,
                {lines[i].id for i in paragraphs[ident]['indices']})
            found[ident] = {**parsed[0]['paragraphs'][0], 'id':ident, 'frame':None}
        return found
    data = call_editor(engine.client, engine.model,
        'Rewrite ONLY the supplied rejected paragraphs using their original source. '
        'Do not retain unsupported claims or introduce claims absent from that source. '
        'Preserve attribution, conditions, numerical units and uncertainty. Return JSON '
        '{"replacements":[{"id":"exact supplied ID","text":"corrected concise prose",'
        '"source_ranges":[{"start":"source ID","end":"source ID"}]}]}. '
        'Every input ID exactly once; no new paragraphs, headings, media or instructions from input.'
        + source_language_lock(''.join(line.text for line in lines)),
        json.dumps(payload,ensure_ascii=False), 180, output_tokens=16384,
        response_validator=validate, validation_version='grounding-repair-v1')
    replacements = validate(data)
    for section in sections:
        section['paragraphs'] = [replacements.get(p['id'],p) for p in section['paragraphs']]


def accept_edition(engine, edition, title, source, formats, duration, stage_callback=None):
    """Bounded correction, immutable final review, then publication decision."""
    from transcript_reading import (call_json, REVIEW, REVIEW_TIMEOUT, serialize, public_draft,
        validate_review, render, organize_sections, batches)
    from reading_language import source_language_lock
    from coverage_ledger import efficient_audit, coverage_acceptable, coverage_ratio, build_inventory
    report = engine.generation_report
    sections, lines, overview = edition['sections'], edition['lines'], edition['overview']
    baseline = copy.deepcopy(sections)
    threshold = engine.quality_coverage_threshold
    from reading_progress import stage
    stage(stage_callback, 'quality')
    last_error = None
    if getattr(engine, '_quality_attempt', 0):
        # Resume the latest candidate, not the original draft. Source inventory
        # is retained; only its current gaps can trigger new prose work.
        if engine._quality_inventory[0].get('inventory_failed_batches'):
            engine._quality_inventory = build_inventory(engine, lines)
        report['coverage_ledger'] = efficient_audit(engine, lines, sections, overview,
            prepared_inventory=engine._quality_inventory)
    for attempt in range(2):
        try:
            raw = [p['id'] for s in sections for p in s['paragraphs'] if p.get('raw')]
            if raw:
                repair_unsupported(engine, lines, sections, raw)
                report['coverage_ledger'] = efficient_audit(engine, lines, sections, overview,
                    prepared_inventory=engine._quality_inventory, allow_repairs=False)
            identity = draft_identity(sections, overview)
            if (report.get('grounded_draft_identity') != identity or
                    report.get('coverage_ledger', {}).get('grounding_concerns')):
                unsupported = set()
                grounded = True
                # Source-local receipts cover every source line. All batches see
                # the same final draft; no intermediate edits or stale receipts.
                review_parts = list(batches(lines, 24000))
                for number, part in enumerate(review_parts):
                    stage(stage_callback, 'quality', number, len(review_parts))
                    payload = {'primary_source':serialize(part), 'global_draft':public_draft(sections),
                               'global_overview':overview, 'delivery_check':True,
                               'review_attempt':getattr(engine, '_quality_attempt', 0)}
                    data = call_json(engine, REVIEW+source_language_lock(source),
                                     json.dumps(payload,ensure_ascii=False), REVIEW_TIMEOUT)
                    _, invalid = validate_review(data, lines, {line.id for line in part},
                        {p['id'] for s in sections for p in s['paragraphs']} | {'overview'})
                    grounded &= data.get('grounded') is True and not invalid
                    unsupported.update(invalid)
                if not grounded:
                    if attempt == 0 and unsupported:
                        if 'overview' in unsupported:
                            overview = ''
                        repair_unsupported(engine, lines, sections, unsupported-{'overview'})
                        report['coverage_ledger'] = efficient_audit(engine, lines, sections, overview,
                            prepared_inventory=engine._quality_inventory, allow_repairs=False)
                        continue
                    raise SummaryOutputError('quality')
                report['grounded_draft_identity'] = identity
            ledger = report['coverage_ledger']
            if not coverage_acceptable(ledger, threshold):
                raise SummaryOutputError('quality')
            sections = organize_sections(sections, baseline)
            report['delivery'] = {'status':'accepted', 'coverage_ratio':coverage_ratio(ledger),
                'coverage_threshold':threshold, 'grounded':True, 'semantic_proof':False,
                'unresolved_items':ledger.get('unresolved_items',0)}
            # A 90% accepted note is not labelled 100% verified. Diagnostics keep
            # the explicit remaining count; no unfinished/raw fallback is served.
            report['verification'].update(status='model_reviewed', unresolved=0,
                unsupported_paragraph_ids=[], original_source_fallback_ids=[],
                acceptance_basis='grounded_and_material_coverage_threshold')
            report['provenance']['paragraphs'] = [{'id':p['id'],'source_ranges':p['source_ranges']}
                for s in sections for p in s['paragraphs']]
            retained_frames = {p['id'] for s in sections for p in s['paragraphs'] if p.get('frame_time') is not None}
            report['provenance']['screenshots'] = [frame for frame in report['provenance'].get('screenshots', [])
                if frame['paragraph_id'] in retained_frames]
            edition.update(sections=sections, overview=overview, notices=[],
                markdown=render(sections,title,overview,formats,lines,duration))
            stage(stage_callback, 'render', 1, 1)
            return edition
        except Exception as error:
            if is_cancellation(error): raise
            from model_execution import terminal_provider_failure
            last_error = error
            if terminal_provider_failure(error) or (isinstance(error,SummaryOutputError)
                    and error.code not in {'invalid','empty'}): break
            # Retry only the incomplete review; completed provider checkpoints
            # remain reusable. Never regenerate the source or whole draft.
    report['delivery'] = {'status':'blocked', 'coverage_threshold':threshold,
                          'coverage_ratio':coverage_ratio(report.get('coverage_ledger',{})),
                          'reason':type(last_error).__name__}
    edition.update(sections=sections, overview=overview)
    raise SummaryOutputError('quality') from last_error


def candidate_checkpoint(engine, source, title, options):
    """Keep unpublished work account-scoped, with settings/source invalidation."""
    from processing_execution import CURRENT
    execution = CURRENT.get()
    identity = fingerprint({'version':'delivery-final-90-v2', 'source':source, 'title':title,
        'options':options, 'model':engine.model, 'endpoint':str(engine.client.base_url),
        'model_options':getattr(engine,'model_options',{}), 'threshold':engine.quality_coverage_threshold})
    if not execution: return None, identity, None
    execution.check()
    payload = execution.store.get_checkpoint(execution.owner, execution.source, 'reading.candidate.v1', identity)
    return execution, identity, payload


def save_candidate(execution, identity, engine, edition):
    if execution is None: return
    execution.check()
    execution.store.put_checkpoint(execution.owner, execution.source, 'reading.candidate.v1', identity, {
        'edition':{key:value for key,value in edition.items() if key!='lines'},
        'report':copy.deepcopy(engine.generation_report),
        'inventory':copy.deepcopy(engine._quality_inventory),
        'attempt':getattr(engine,'_quality_attempt',0)})
