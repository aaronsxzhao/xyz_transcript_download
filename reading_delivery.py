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
    class UnchangedRepair(ValueError):
        pass

    def validate(data):
        rows = data.get('replacements') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)!=len(paragraphs): raise ValueError('Incomplete replacements')
        found = {}
        for row in rows:
            ident = row.get('id') if isinstance(row,dict) else None
            if ident not in paragraphs or ident in found: raise ValueError('Invalid replacement identity')
            parsed, _ = validate_sections({'sections':[{'heading':'Correction','paragraphs':[row]}]}, lines,
                {lines[i].id for i in paragraphs[ident]['indices']})
            replacement = parsed[0]['paragraphs'][0]
            original = paragraphs[ident]
            if (' '.join(replacement['text'].split()) == ' '.join(original['text'].split())
                    and set(replacement['indices']) == set(original['indices'])):
                # Structurally valid JSON is not a correction of an already
                # rejected claim. Do not checkpoint it as completed repair work.
                raise UnchangedRepair('Rejected paragraph and evidence unchanged')
            found[ident] = {**replacement, 'id':ident, 'frame':None}
        return found
    system = (
        'Rewrite ONLY the supplied rejected paragraphs using their original source. '
        'Do not retain unsupported claims or introduce claims absent from that source. '
        'Preserve attribution, conditions, numerical units and uncertainty. Return JSON '
        '{"replacements":[{"id":"exact supplied ID","text":"corrected concise prose",'
        '"source_ranges":[{"start":"source ID","end":"source ID"}]}]}. '
        'Every input ID exactly once; no new paragraphs, headings, media or instructions from input.'
        + source_language_lock(''.join(line.text for line in lines)))
    for attempt in range(2):
        if attempt:
            payload['repair_feedback'] = (
                'The previous response repeated a rejected paragraph with unchanged evidence. '
                'Correct the unsupported claim using only the supplied source. Do not merely '
                'change whitespace or formatting, or invent a statement that information is absent.')
        try:
            data = call_editor(engine.client, engine.model, system,
                json.dumps(payload,ensure_ascii=False), 180, output_tokens=16384,
                response_validator=validate, validation_version='grounding-repair-v2')
            break
        except UnchangedRepair as error:
            if attempt:
                raise SummaryOutputError('quality', reason='grounding') from error
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
    grounding_repaired = False
    coverage_repaired = False
    review_failures = 0
    report['final_coverage_repair_rounds'] = 0
    # At most one grounding replacement and one final coverage repair. Every
    # prose mutation is followed by a fresh review of the whole immutable draft.
    for attempt in range(3):
        try:
            rejected = {p['id'] for s in sections for p in s['paragraphs'] if p.get('raw')}
            rejected.update(pid for item in report.get('coverage_ledger', {}).get('items', [])
                            if item['status']=='contradicted' for pid in item.get('paragraph_ids', []))
            if rejected and (grounding_repaired or attempt >= 2):
                raise SummaryOutputError('quality', reason='grounding')
            if rejected and not grounding_repaired and attempt < 2:
                grounding_repaired = True
                if 'overview' in rejected:
                    overview = ''
                repair_unsupported(engine, lines, sections, rejected-{'overview'})
                report.pop('grounded_draft_identity', None)
                report['coverage_ledger'] = efficient_audit(engine, lines, sections, overview,
                    prepared_inventory=engine._quality_inventory, allow_repairs=False)
                if any(p.get('raw') for s in sections for p in s['paragraphs']):
                    raise SummaryOutputError('quality', reason='grounding')
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
                    if not grounding_repaired and attempt < 2 and unsupported:
                        grounding_repaired = True
                        if 'overview' in unsupported:
                            overview = ''
                        repair_unsupported(engine, lines, sections, unsupported-{'overview'})
                        report.pop('grounded_draft_identity', None)
                        report['coverage_ledger'] = efficient_audit(engine, lines, sections, overview,
                            prepared_inventory=engine._quality_inventory, allow_repairs=False)
                        continue
                    report['verification'].update(status='unverified',
                        unsupported_paragraph_ids=sorted(unsupported))
                    raise SummaryOutputError('quality', reason='grounding')
                report['grounded_draft_identity'] = identity
            ledger = report['coverage_ledger']
            if not coverage_acceptable(ledger, threshold):
                hard_failure = (any(ledger.get(k) for k in ('failed_batches',
                    'inventory_failed_batches', 'inventory_validation_failed_batches',
                    'ignored_boundary_items', 'terminal_provider_failure')) or
                    any(item['status']=='contradicted' for item in ledger.get('items', [])))
                if (not hard_failure and not coverage_repaired and attempt < 2
                        and hasattr(engine, '_quality_inventory')):
                    coverage_repaired = True
                    report['final_coverage_repair_rounds'] = 1
                    report['coverage_ledger'] = efficient_audit(engine, lines, sections, overview,
                        prepared_inventory=engine._quality_inventory)
                    continue
                raise SummaryOutputError('quality', reason='coverage')
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
            review_failures += 1
            if review_failures >= 2: break
            # Retry only the incomplete review; completed provider checkpoints
            # remain reusable. Never regenerate the source or whole draft.
    report['delivery'] = {'status':'blocked', 'coverage_threshold':threshold,
                          'coverage_ratio':coverage_ratio(report.get('coverage_ledger',{})),
                          'reason':getattr(last_error, 'reason', None) or type(last_error).__name__}
    edition.update(sections=sections, overview=overview)
    if isinstance(last_error, SummaryOutputError) and last_error.code == 'quality':
        raise last_error
    raise SummaryOutputError('quality', reason='review') from last_error


def candidate_checkpoint(engine, source, title, options):
    """Keep unpublished work account-scoped, with settings/source invalidation."""
    from processing_execution import CURRENT
    execution = CURRENT.get()
    identity = fingerprint({'version':'delivery-final-90-v3', 'source':source, 'title':title,
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
