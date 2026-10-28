"""Bounded reading synthesis with two calls per section and lossless fallback.

This edits audited notes, not raw transcripts. Stable references retain the
ability to check every argument without requiring a paragraph for every note.
"""
import json
import re
import time

from reading_budget import PLAN, units, visible_prose
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


def _source_groups(items, count, language):
    """Balanced contiguous groups; source membership never comes from a model."""
    remaining = list(items)
    groups = []
    weights = [max(1,units(visible_prose(row['text']),language)) for row in remaining]
    for index in range(count):
        left = count-index
        if left == 1:
            groups.append(remaining)
            break
        aim = sum(weights)/left
        size = 0
        end = 0
        while end < len(remaining)-(left-1) and (size < aim or not end):
            size += weights[end]
            end += 1
        groups.append(remaining[:end])
        remaining = remaining[end:]
        weights = weights[end:]
    return groups


def edit_whole_note(items, call, checkpoint=None, *, preserve_order=False,
                    source_text='', report=None, reserved_text=''):
    from math import ceil
    from reading_editor import _media, _verbatim_blocks
    from note_presentation import normalize_media_markers
    from processing_execution import parallel_map
    from source_coverage import SOURCE_FIDELITY
    from reading_prompts import ARGUMENT_CONTRACT
    report = report if report is not None else {}
    report.update(strategy='fixed_source_sections', input_sections=len(items),
                  composed_batches=0, retained_batches=0, model_calls=0)
    def original(rows):
        return [dict(row, ids=[row['id']], evidence_id=row['id']) for row in rows]
    if not items:
        return []
    plan = PLAN.get() or {}
    language = plan.get('language', 'en')
    reserved = units(visible_prose(reserved_text), language)
    target = max(1, round(plan.get('target_high', 0))-reserved)
    rows = [{**row, 'text':normalize_media_markers(row['text'])} for row in items]
    report.update(reserved_units=reserved, body_budget=target)
    # Evidence is retained by the application. The model chooses its original
    # note ID from the explanation, without recopying thousands of quoted words.
    if sum(len(row['text']) for row in rows) > MAX_INPUT_CHARS:
        report.update(fallback_reason='input_capacity', retained_batches=1,
                      output_sections=len(rows), target_met=False)
        return original(rows)
    source_units = sum(max(1,units(visible_prose(row['text']),language)) for row in rows)
    section_size = 400 if language == 'zh' else 230
    count = min(len(rows),max(1,ceil(min(target,source_units)/section_size)))
    grouped = _source_groups(rows,count,language)
    weights = [sum(max(1,units(visible_prose(row['text']),language)) for row in group) for group in grouped]
    total = sum(weights)
    boundaries = [round(target*sum(weights[:i])/total) for i in range(len(weights)+1)]
    lookup = {}
    requests = []
    for i,group in enumerate(grouped):
        key = f'G{i+1}'
        budget = max(1,boundaries[i+1]-boundaries[i])
        lookup[key] = group
        requests.append({'id':key, 'body_budget':budget,
            'writing_target':max(1,round(budget*plan.get('target_low',target)/max(1,plan.get('target_high',target)))),
            'notes':[{'id':row['id'],'topic':row['topic'],
                      'text':_separate_media(row['text'])[0],
                      'has_original_quote':bool(row.get('evidence'))} for row in group]})
    # Bound RESPONSE size as well as input size: Chinese output can time out
    # even when the request itself is small. Keep independent calls at two.
    batches = []
    batch = []
    characters = output_budget = 0
    for request in requests:
        size = len(json.dumps(request,ensure_ascii=False))
        if batch and (characters+size>24000 or output_budget+request['body_budget']>1200):
            batches.append(batch);batch=[];characters=output_budget=0
        batch.append(request);characters+=size;output_budget+=request['body_budget']
    if batch:batches.append(batch)
    common = SOURCE_FIDELITY + ARGUMENT_CONTRACT + source_language_lock(source_text) + """
READING EDITION, not a catalogue or sentence-by-sentence retelling.
The application has fixed consecutive source groups. Return exactly ONE section
per group id, in any order; the application restores source order and media.
Never merge groups, invent group IDs, or return lists of source IDs.
section.id must copy group.id; evidence_id copies a note.id inside that group. Each section
may contain several connected paragraphs, a comparison table or genuine steps.
Keep the meaningful source headings and original language. Use the same broad
topic for adjacent sections of the same discussion. Select central claims,
decisive reasoning, informative evidence, disagreements and necessary conditions.
Remove repeated explanations, scene-setting and biographical detail that does
not help interpret the argument. Do not repeat introductions or closing recaps.
Aim for writing_target, leaving body_budget as room for essential qualifications.
These budgets exclude original quotes. Never pad or truncate to hit a count.
Original quotations are retained separately; evidence_id selects a note within
THIS group whose evidence best supports the explanation. Do not invent quotes.
Preserve existing quote/code blocks verbatim and ordinary source URLs. Media
markers and screenshots are restored by the application; do not generate them.
Do not carry forward extraction commentary declaring a question unanswered just
because earlier notes lacked its answer. Preserve uncertainty explicitly stated
by speakers, and connect questions to answers in the supplied notes when present.
"""
    def measured(section):
        value = section['heading']+'\n'+section['text']
        if preserve_order:value = section['topic']+'\n'+value
        return units(visible_prose(value),language)
    def work(batch):
        stats = {'model_calls':0,'composed_sections':0,'retained_sections':0}
        expected = {row['id']:row for row in batch}
        deadline = time.monotonic()+240
        def request(system,payload):
            if checkpoint:checkpoint()
            remaining = deadline-time.monotonic()
            if remaining<1:raise TimeoutError('Reading section deadline exhausted')
            stats['model_calls']+=1
            response = call(common+system,json.dumps(payload,ensure_ascii=False),min(120,remaining))
            if checkpoint:checkpoint()
            return response if isinstance(response,dict) else {}
        def indexed(values):
            found = {};duplicates=set()
            for value in values if isinstance(values,list) else []:
                if not isinstance(value,dict):continue
                key = str(value.get('id','')).strip().upper()
                if key not in expected:continue
                if key in found:duplicates.add(key)
                found[key]=value
            return {key:value for key,value in found.items() if key not in duplicates}
        def validate(key,value):
            if not all(isinstance(value.get(field),str) and value[field].strip() for field in ('topic','heading','text')):
                raise ValueError('output_shape')
            text = normalize_media_markers(value['text'])
            if _separate_media(text)[1]:raise ValueError('unexpected_media')
            source = '\n\n'.join(row['text'] for row in lookup[key])
            media = [marker for row in lookup[key] for marker in _separate_media(row['text'])[1]]
            rendered = text+('\n\n'+'\n\n'.join(media) if media else '')
            if _media(source) != _media(rendered):raise ValueError('source_media')
            blocks = _verbatim_blocks(source)
            if any(block not in text for block in blocks) or any(block not in blocks for block in _verbatim_blocks(text)):
                raise ValueError('verbatim_source')
            return {**value,'text':rendered}
        accepted = {}
        reasons = {}
        def retained(reason):
            reasons[reason] = reasons.get(reason,0)+1
        try:
            schema = {'sections':[{'id':batch[0]['id'], 'topic':'broad source chapter',
                'heading':'specific claim','text':'concise connected Markdown explanation',
                'evidence_id':'a note.id from this group'}]}
            draft = request('Return JSON in this shape, with one section per supplied group: '+json.dumps(schema),
                            {'groups':batch})
            sections = indexed(draft.get('sections'))
            feedback = {}
            sizes = {}
            for key in expected:
                value = sections.get(key)
                if value is None:
                    feedback[key]='missing_or_duplicate_section';continue
                if all(isinstance(value.get(field),str) for field in ('topic','heading','text')):
                    sizes[key]=measured(value)
                try:validate(key,value)
                except ValueError as error:feedback[key]=str(error)
            review = request("""
Independently compare each rewrite with ALL notes in its own group. Judge
important meaning, not copying every anecdote. Correct factual errors, missing
qualifications and structural errors. If draft_units exceeds that group's
body_budget, compress toward writing_target, removing repetition and setup first.
Return JSON with "checks" (one object per supplied group.id, complete and grounded
booleans) and "sections" (only corrected sections in the original schema).
A check judges the corrected section when one is supplied. Check every group;
do not discard good sections because a different group needs repair. If a
section is missing, reconstruct it from that group's notes within its budget.
Do not add prose unrelated to a repair. Do not restate the input in full.
""",{'groups':batch,'rewrite':draft.get('sections'),
      'validation_feedback':feedback,'draft_units':sizes})
            repairs = indexed(review.get('sections'))
            checks = indexed(review.get('checks'))
            for key in expected:
                check = checks.get(key,{})
                if check.get('complete') is not True or check.get('grounded') is not True:
                    retained('semantic_review' if check else 'missing_review')
                    continue
                value = repairs.get(key,sections.get(key))
                if value is None:
                    retained('missing_section');continue
                try:accepted[key]=validate(key,value)
                except ValueError as error:
                    retained(str(error));continue
            stats['review_repairs']=len(repairs)
        except Exception as error:
            if is_cancellation(error):raise
            stats['fallback_reason']=type(error).__name__
        stats['retention_reasons']=reasons
        result = []
        for key in expected:
            value = accepted.get(key)
            group = lookup[key]
            if value is None:
                result.extend(original(group));stats['retained_sections']+=1
                continue
            ids = [row['id'] for row in group]
            evidence = value.get('evidence_id')
            if evidence not in ids:
                evidence = next((row['id'] for row in group if row.get('evidence')),ids[0])
            result.append({'topic':value['topic'].lstrip('# ').strip(),
                'text':'#### '+value['heading'].lstrip('# ').strip()+'\n\n'+value['text'].strip(),
                'ids':ids,'evidence_id':evidence})
            stats['composed_sections']+=1
        return result,stats
    results = parallel_map(work,batches,workers=2) if len(batches)>1 else [work(batches[0])]
    output = [row for result,_ in results for row in result]
    stats = [stat for _,stat in results]
    measured_output = sum(units(visible_prose(row['text']),language) for row in output)
    if preserve_order:
        previous=None
        for row in output:
            if row['topic']!=previous:measured_output+=units(visible_prose(row['topic']),language)
            previous=row['topic']
    report.update(batches=stats,source_groups=len(grouped),
        model_calls=sum(s['model_calls'] for s in stats),
        composed_batches=sum(bool(s['composed_sections']) for s in stats),
        retained_batches=sum(bool(s['retained_sections']) for s in stats),
        output_sections=len(output),output_units=measured_output,
        target_met=measured_output<=target)
    return output
