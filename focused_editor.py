"""Bounded reading synthesis with two calls per section and lossless fallback.

This edits audited notes, not raw transcripts. Stable references retain the
ability to check every argument without requiring a paragraph for every note.
"""
import json
import re
import time

from reading_budget import PLAN, guidance, units, visible_prose
from reading_language import source_language_lock
from summary_errors import is_cancellation

MAX_INPUT_CHARS = 160000


def _separate_media(text):
    """Keep generated media as application-owned data, outside model prose.

    Never extract markers inside source quotations/code or ordinary text links.
    IDs later attach these exact markers to the same merged discussion.
    """
    from markdown_it import MarkdownIt
    lines = text.splitlines(keepends=True)
    protected = set()
    for token in MarkdownIt().parse(text):
        if token.map and token.type in ('blockquote_open', 'fence', 'code_block'):
            protected.update(range(*token.map))
    pattern = re.compile(r'!\[Screenshot at \d+(?::\d+){1,2}\]\([^\n)]+\)|(?:Screenshot-|\*?Content-)\[\d+(?::\d+){1,2}\]|(?m:^\[\d+(?::\d+){1,2}\][ \t]*$)')
    media = []
    def take(match):
        media.append(match[0])
        return ''
    prose = ''.join(line if i in protected else pattern.sub(take, line) for i, line in enumerate(lines))
    return prose, media


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
        outline = list(dict.fromkeys(r['topic'] for r in rows))
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
    model_rows = []
    media_by_id = {}
    for row in rows:
        prose, media = _separate_media(row['text'])
        media_by_id[row['id']] = media
        model_rows.append({**row, 'text': prose})
    deadline = time.monotonic() + 240
    common = source_language_lock(source_text) + guidance(share=share)
    common += '''
WHOLE DOCUMENT SYNTHESIS, not a rewrite of each input card:
Only IDs in notes belong to this request. document_outline is context only.
The application retains media markers and screenshots by input ID. Do not
generate media markers or invent timestamps; concentrate on the reading prose.
Credentials, scene setting and conversation setup are not central arguments.
Omit them unless they are necessary to interpret the claim or its evidence.
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
The application attaches original media to each paragraph using its IDs. Do not move a later
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
        try:
            _partition(paragraphs, lookup)
        except ValueError as error:
            raise ValueError('source_references') from error
        output = []
        for p in paragraphs:
            if (not isinstance(p.get('text'), str) or not p['text'].strip()
                    or not isinstance(p.get('heading'), str) or not p['heading'].strip()
                    or not isinstance(p.get('topic'), str) or not p['topic'].strip()
                    or p.get('evidence_id') not in p['ids']):
                raise ValueError('output_shape')
            ids = sorted(p['ids'], key=order.__getitem__)
            if preserve_order and [order[i] for i in ids] != list(range(order[ids[0]], order[ids[-1]]+1)):
                raise ValueError('source_order')
            text = normalize_media_markers(p['text'])
            _, invented_media = _separate_media(text)
            if invented_media:
                raise ValueError('unexpected_media')
            media = [marker for ident in ids for marker in media_by_id[ident]]
            if media:
                text += '\n\n' + '\n\n'.join(media)
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
        if preserve_order:
            # Whole paragraphs can be restored to chronology without rewriting
            # their meaning. Interleaved source groups above still need repair.
            output.sort(key=lambda p: order[p['ids'][0]])
        return output

    def length(paragraphs):
        total = 0
        topic = None
        for p in paragraphs:
            total += units(visible_prose(p['heading']+'\n'+p['text']), language)
            if preserve_order and p.get('topic') != topic:
                topic = p.get('topic')
                total += units(visible_prose(topic or ''), language)
        return total

    try:
        aim = max(1, round(target * plan.get('target_low', target) / max(1, plan.get('target_high', target))))
        draft = request(COMPOSE + '\nAim for writing_target; body_budget is room for indispensable qualifications, not a length to fill.\n',
                        {'notes': model_rows, 'writing_target': aim, 'body_budget': target, 'document_outline': _outline or []})
        draft_error = None
        raw = draft.get('paragraphs')
        # Count readable prose even when IDs/order need repair. Previously a
        # reference error hid over-budget length from the final reviewer.
        if isinstance(raw, list) and all(isinstance(p, dict) and isinstance(p.get('heading'),str) and isinstance(p.get('text'),str) for p in raw):
            report['draft_units'] = length(raw)
        try:
            paragraphs = validate(draft.get('paragraphs'))
            report['draft_units'] = length(paragraphs)
        except ValueError as error:
            # The second, already-budgeted review can repair a reference typo
            # while checking semantics; do not discard all prose after one typo.
            paragraphs = None
            draft_error = str(error)
            report['draft_validation'] = draft_error
        # One independent review, with local factual and length repairs in the
        # same response. No separate planning call or per-chapter review cascade.
        review = request(VERIFY + '''
This is the final whole-note review. Preserve the topic field in any repair.
If validation_feedback is present, correct the structural problem and return
a COMPLETE paragraphs array. Only notes IDs are valid and each must occur once.
Media is restored by the application; return prose without generated media markers.
Check completeness and grounding of your corrected prose in this same response.
Correct source references without expanding otherwise correct passages. For video,
N1,N3 cannot form a group while N2 is elsewhere: use consecutive source ranges.
When draft_units exceeds body_budget, compress toward writing_target, not merely
a few words below the draft. Remove scene-setting and repeated explanations
first; keep important evidence, disagreements and meaning-changing conditions.
If draft_units exceeds body_budget, return a COMPLETE corrected paragraphs array
that removes repetition and lower-value retelling while retaining the important
claims, decisive evidence, disagreements and meaning-changing conditions.
Aim within body_budget; do not truncate or manufacture claims. Review the
corrected version when setting complete/grounded. Do not expand merely to give
each input id its own paragraph. Quotes are separate evidence, not reading prose.
''', {'notes': model_rows, 'rewrite': draft.get('paragraphs'), 'draft_units': report.get('draft_units'),
       'validation_feedback': draft_error, 'body_budget': target, 'writing_target': aim})
        if review.get('complete') is not True or review.get('grounded') is not True:
            raise ValueError('semantic_review')
        if 'paragraphs' in review:
            paragraphs = validate(review['paragraphs'])
            report['review_repairs'] = 1
        if paragraphs is None:
            raise ValueError(draft_error or 'output_shape')
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
            'source_media','media_order','verbatim_source','source_order','semantic_review','output_shape','unexpected_media','source_references'
        } else type(error).__name__
        report.update(fallback_reason=reason, retained_batches=1, output_sections=len(items), target_met=False)
        return originals
