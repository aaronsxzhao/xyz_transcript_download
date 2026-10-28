"""Bounded reading synthesis with two calls per section and lossless fallback.

This edits audited notes, not raw transcripts. Stable references retain the
ability to check every argument without requiring a paragraph for every note.
"""
import json
import time

from reading_budget import PLAN, guidance, units, visible_prose
from reading_language import source_language_lock
from summary_errors import is_cancellation

MAX_INPUT_CHARS = 160000


def edit_whole_note(items, call, checkpoint=None, *, preserve_order=False,
                    source_text='', report=None, reserved_text='', _body_budget=None, _outline=None):
    from reading_editor import COMPOSE, VERIFY, _partition, _media, _verbatim_blocks
    from note_presentation import normalize_media_markers, media_times
    report = report if report is not None else {}
    report.update(strategy='whole_note', input_sections=len(items), composed_batches=0,
                  retained_batches=0, model_calls=0)
    originals = [dict(item, ids=[item['id']], evidence_id=item['id']) for item in items]
    if not items:
        return originals
    plan = PLAN.get() or {}
    language = plan.get('language', 'en')
    # Count the actual visible introduction/conclusion, never folded quotes.
    reserved = units(visible_prose(reserved_text), language)
    target = max(1, round(plan.get('target_high', 0)) - reserved) if _body_budget is None else _body_budget
    report.update(reserved_units=reserved, body_budget=target)
    share = target / max(1, plan.get('target_high', 0))
    rows = [{**item, 'text': normalize_media_markers(item['text'])} for item in items]
    payload = json.dumps({'notes': rows}, ensure_ascii=False)
    if len(payload) > MAX_INPUT_CHARS:
        report.update(fallback_reason='input_capacity', retained_batches=1,
                      output_sections=len(items), target_met=False)
        return originals
    # Long output JSON can exceed one provider response deadline. Use a few
    # contiguous sections, not a separate call cascade for every source card.
    if _body_budget is None and len(payload) > 24000 and len(rows) > 1:
        from reading_editor import _batches
        from processing_execution import parallel_map
        batches = list(_batches(rows, max(24000, (len(payload) + 2) // 3)))
        weights = [max(1, units(visible_prose('\n'.join(r['text'] for r in batch)), language)) for batch in batches]
        total = sum(weights)
        # Allocate exactly the remaining document budget, without multiplying it.
        boundaries = [round(target * sum(weights[:i]) / total) for i in range(len(weights)+1)]
        outline = [{'id':r['id'], 'topic':r['topic']} for r in rows]
        def edit_batch(index):
            child = {}
            result = edit_whole_note(batches[index], call, checkpoint,
                preserve_order=preserve_order, source_text=source_text, report=child,
                _body_budget=max(1, boundaries[index+1]-boundaries[index]), _outline=outline)
            return result, child
        results = parallel_map(edit_batch, range(len(batches)), workers=2)
        output = [item for result, _ in results for item in result]
        children = [child for _, child in results]
        report.update(strategy='bounded_document_sections', batches=children,
            model_calls=sum(c['model_calls'] for c in children),
            composed_batches=sum(c['composed_batches'] for c in children),
            retained_batches=sum(c['retained_batches'] for c in children),
            output_sections=len(output),
            target_met=all(c.get('target_met', False) for c in children))
        return output
    order = {row['id']: i for i, row in enumerate(rows)}
    lookup = {row['id']: row for row in rows}
    deadline = time.monotonic() + 240
    common = source_language_lock(source_text) + guidance(share=share)
    common += '''
WHOLE DOCUMENT SYNTHESIS, not a rewrite of each input card:
First identify the central answers and rank their supporting arguments. Group
related evidence under those answers. Merge restatements across the complete
note. Select the strongest explanatory example; include another only when it
adds a different mechanism, exception or decisive evidence. Preserve meaningful
source headings, but input cards and chunk boundaries are NOT mandatory headings.
Account for every input id through the argument that represents its meaning;
this does NOT require reproducing every sentence or giving every id a paragraph.
Use a few substantial chapters with connected explanations, not dozens of tiny
chapters. Do not duplicate conclusions in chapter endings. Assign each paragraph
an additional "topic" field naming its broad chapter. No process commentary.
'''
    if preserve_order:
        common += '''
VIDEO: Paragraphs follow source order and cover consecutive input IDs. Combine
adjacent discussions generously. When a topic returns later, explain only its
NEW evidence or qualification rather than repeating the earlier explanation.
Keep media anchors with their discussion in original order. Repeated anchors at
the same instant may be consolidated, but never drop a distinct media link. Do not move a later
example, book, step or objection into an earlier paragraph.
'''

    def request(system, body):
        if checkpoint:
            checkpoint()
        remaining = deadline - time.monotonic()
        if remaining < 1:
            raise TimeoutError('Whole-note deadline exhausted')
        report['model_calls'] += 1
        response = call(system + common, json.dumps(body, ensure_ascii=False), min(120, remaining))
        if checkpoint:
            checkpoint()
        return response

    def validate(paragraphs):
        _partition(paragraphs, lookup)
        output = []
        flattened = []
        for p in paragraphs:
            if (not isinstance(p.get('text'), str) or not p['text'].strip()
                    or not isinstance(p.get('heading'), str) or not p['heading'].strip()
                    or not isinstance(p.get('topic'), str) or not p['topic'].strip()
                    or p.get('evidence_id') not in p['ids']):
                raise ValueError('output_shape')
            ids = sorted(p['ids'], key=order.__getitem__)
            flattened.extend(ids)
            text = normalize_media_markers(p['text'])
            original = '\n\n'.join(lookup[i]['text'] for i in ids)
            # Compare canonical anchors, not optional Markdown asterisks. Do not
            # move all charts to the end or silently reattach them to new claims.
            if not _media(original).issubset(_media(text)):
                raise ValueError('source_media')
            if preserve_order:
                from itertools import groupby
                before = [stamp for stamp, _ in groupby(media_times(original))]
                after = [stamp for stamp, _ in groupby(media_times(text))]
                if after != before:
                    report['media_order_mismatch'] = {'before': before, 'after': after}
                    raise ValueError('media_order')
            if any(block not in text for i in ids for block in _verbatim_blocks(lookup[i]['text'])):
                raise ValueError('verbatim_source')
            output.append({**p, 'ids': ids, 'text': text})
        if preserve_order and flattened != list(lookup):
            raise ValueError('source_order')
        return output

    def length(paragraphs):
        return sum(units(visible_prose(p['heading']+'\n'+p['text']), language) for p in paragraphs)

    try:
        draft = request(COMPOSE, {'notes': rows, 'body_budget': target, 'document_outline': _outline or []})
        paragraphs = validate(draft.get('paragraphs'))
        report['draft_units'] = length(paragraphs)
        # One independent review, with local factual and length repairs in the
        # same response. No separate planning call or per-chapter review cascade.
        review = request(VERIFY + '''
This is the final whole-note review. Preserve the topic field in any repair.
If draft_units exceeds body_budget, return a COMPLETE corrected paragraphs array
that removes repetition and lower-value retelling while retaining the important
claims, decisive evidence, disagreements and meaning-changing conditions.
Aim within body_budget; do not truncate or manufacture claims. Review the
corrected version when setting complete/grounded. Do not expand merely to give
each input id its own paragraph. Quotes are separate evidence, not reading prose.
''', {'notes': rows, 'rewrite': paragraphs, 'draft_units': length(paragraphs),
       'body_budget': target})
        if review.get('complete') is not True or review.get('grounded') is not True:
            raise ValueError('semantic_review')
        if 'paragraphs' in review:
            paragraphs = validate(review['paragraphs'])
            report['review_repairs'] = 1
        measured = length(paragraphs)
        report.update(composed_batches=1, output_sections=len(paragraphs), output_units=measured,
                      body_budget=target, target_met=measured <= target)
        if measured > target:
            report['budget_unresolved'] = True
        return [{'topic': p['topic'].lstrip('# ').strip(),
                 'text': '#### '+p['heading'].lstrip('# ').strip()+'\n\n'+p['text'].strip('\r\n'),
                 'ids': p['ids'], 'evidence_id': p['evidence_id']} for p in paragraphs]
    except Exception as error:
        if is_cancellation(error):
            raise
        reason = str(error) if type(error) is ValueError and str(error) in {
            'source_media','media_order','verbatim_source','source_order','semantic_review','output_shape'
        } else type(error).__name__
        report.update(fallback_reason=reason, retained_batches=1, output_sections=len(items), target_met=False)
        return originals
