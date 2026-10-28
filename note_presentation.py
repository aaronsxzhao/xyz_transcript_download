"""Lossless video ordering and bounded language-only correction of generated prose."""
import re
import time
from collections import Counter

from markdown_it import MarkdownIt
from reading_language import chinese_source, source_language_lock
from summary_errors import is_cancellation


def _sections(markdown, levels=(2,)):
    lines=markdown.splitlines(keepends=True)
    tokens=[t for t in MarkdownIt().parse(markdown) if t.type=='heading_open' and t.level==0 and int(t.tag[1:]) in levels]
    if not tokens: return '',[markdown]
    return ''.join(lines[:tokens[0].map[0]]),[''.join(lines[t.map[0]:tokens[i+1].map[0] if i+1<len(tokens) else len(lines)]) for i,t in enumerate(tokens)]


def without_generated_toc(markdown):
    prefix,sections=_sections(markdown)
    result=[prefix]
    for section in sections:
        heading,_,body=section.partition('\n')
        name=re.sub(r'^##\s+(?:\d+[.．、]?\s+)?','',heading).strip().casefold()
        tokens=MarkdownIt().parse(body)
        scaffold={'bullet_list_open','bullet_list_close','ordered_list_open','ordered_list_close','list_item_open','list_item_close','paragraph_open','paragraph_close','inline','hr'}
        if name in ('contents','table of contents','目录') and any(t.type.endswith('list_open') for t in tokens) and all(t.type in scaffold for t in tokens) and not any(t.type=='paragraph_open' and t.level==0 for t in tokens):
            continue
        result.append(section)
    return ''.join(result)


def normalize_media_markers(markdown):
    """Repair only generated line-leading markers; never change source times."""
    lines = markdown.splitlines(keepends=True)
    protected = set()
    for token in MarkdownIt().parse(markdown):
        if token.map and token.type in ('fence', 'code_block', 'blockquote_open'):
            protected.update(range(*token.map))
    pattern = re.compile(r'^( {0,3})\*?(Content|Screenshot)-\[?(\d+(?::\d{2}){1,2})\]?\*?(?=\s|$)')
    def repair(match):
        indent, kind, stamp = match.groups()
        if any(int(value) >= 60 for value in stamp.split(':')[1:]):
            return match.group(0)
        return indent + ('*' if kind == 'Content' else '') + kind + '-[' + stamp + ']'
    return ''.join(line if i in protected else pattern.sub(repair, line, count=1)
                   for i, line in enumerate(lines))


def media_times(markdown):
    # Read generated media anchors only, never numbers in prose, quoted examples
    # or URLs' expiry/signature parameters. Keep the first anchor as chapter start.
    lines=markdown.splitlines(keepends=True)
    protected=set()
    for token in MarkdownIt().parse(markdown):
        if token.map and token.type in ('fence','code_block','blockquote_open'):
            protected.update(range(*token.map))
    text=''.join(line for i,line in enumerate(lines) if i not in protected)
    pattern=r'(?:Screenshot-|\*?Content-)\[(\d+(?::\d+){1,2})\]|!\[Screenshot at (\d+(?::\d+){1,2})\]|(?m:^\[(\d+(?::\d+){1,2})\][ \t]*$)'
    result=[]
    for match in re.finditer(pattern,text):
        stamp=match[1] or match[2] or match[3]
        seconds=0
        for part in stamp.split(':'): seconds=seconds*60+int(part)
        result.append(seconds)
    return result


def chronological_chapters(markdown):
    """Move whole anchored chapters with their media, without rewriting content.

    Unanchored material follows its preceding anchored chapter; an unanchored
    introduction remains first. No timestamp is fabricated or changed.
    """
    if not any(t.type=='heading_open' and t.tag=='h2' and t.level==0 for t in MarkdownIt().parse(markdown)):
        return markdown
    prefix,sections=_sections(markdown)
    groups=[];conclusions=[]
    for section in sections:
        heading=re.sub(r'^##\s+(?:\d+[.．、]?\s+)?','',section.split('\n',1)[0]).strip().casefold()
        if heading in ('ai summary','ai 总结','ai总结','section conclusions','分段小结'):
            conclusions.append(section);continue
        parent,separator,body=section.partition('\n')
        introduction,children=_sections(body,(3,))
        units=[introduction+children[0],*children[1:]] if children else [body]
        prefix_parent_written=False
        for unit in units:
            times=media_times(unit)
            if times: groups.append([times[0],parent,unit])
            elif groups and groups[-1][1]==parent: groups[-1][2]+=unit
            elif groups: groups.append([groups[-1][0],parent,unit])
            else:
                # Unanchored subheadings share their existing parent. Repeating
                # it for every child manufactures duplicate chapters.
                prefix+=(parent+separator if not prefix_parent_written else '')+unit
                prefix_parent_written=True
    output=[prefix];previous=None
    for _,parent,body in sorted(groups,key=lambda item:item[0]):
        if previous!=parent:
            if output[-1] and not output[-1].endswith('\n'): output.append('\n\n')
            output.append(parent+'\n')
            if body and not body.startswith(('\n','\r')): output.append('\n')
        output.append(body)
        previous=parent
    if conclusions and output[-1] and not output[-1].endswith('\n'):
        output.append('\n\n')
    return ''.join(output)+''.join(conclusions)


def _protected(markdown):
    lines=markdown.splitlines(keepends=True);offsets=[0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    spans=[]
    for token in MarkdownIt().parse(markdown):
        if token.map and token.type in ('fence','code_block','blockquote_open'):
            start,end=offsets[token.map[0]],offsets[token.map[1]]
            if not spans or start>=spans[-1][1]: spans.append((start,end))
    return spans


def language_mismatch(source,markdown):
    text=markdown
    for left,right in reversed(_protected(text)): text=text[:left]+text[right:]
    text=re.sub(r'(?m)^# [^\n]*\n?', '', text)
    text=re.sub(r'`[^`]*`|https?://[^\s)]+','',text)
    han=len(re.findall(r'[\u3400-\u9fff]',text))
    from reading_language import source_language
    language=source_language(source)
    if language=='en':
        return han>=1
    words=len(re.findall(r'\b[A-Za-z]{2,}\b',text))
    return language=='zh' and words>=40 and han<words/8


def _invariants(text):
    from decimal import Decimal, InvalidOperation
    urls=Counter(re.findall(r'https?://[^\s<>"\)]+|/data/(?:screenshots|thumbnails)/[^\s\)]+|(?:Screenshot-|\*?Content-)\[\d+(?::\d+){1,2}\]',text))
    numbers=Counter()
    multipliers={'万':10000,'萬':10000,'亿':100000000,'億':100000000,'thousand':1000,'million':1000000,'billion':1000000000}
    for match in re.finditer(r'(\d+(?:[.,:]\d+)*)(?:[ \t]*(万|萬|亿|億|thousand\b|million\b|billion\b))?(%)?',text,re.I):
        value,scale,percent=match.groups()
        # Translation may spell 3万 as 30,000; preserve the quantity rather
        # than requiring Chinese typography in an English paragraph.
        if ':' not in value:
            try:
                value=str((Decimal(value.replace(',',''))*multipliers.get((scale or '').lower(),1)).normalize())
            except InvalidOperation:
                pass  # Multi-part software versions remain literal source data.
        numbers[(value,bool(percent))]+=1
    headings=[t.tag for t in MarkdownIt().parse(text) if t.type=='heading_open']
    return urls,numbers,headings


def _language_pieces(markdown):
    """Split large sections at parsed block boundaries, never inside source code."""
    prefix, sections=_sections(markdown,(2,3))
    result=[]
    from markdown_it import MarkdownIt
    for piece in [prefix,*sections]:
        if len(piece)<=12000:
            result.append(piece);continue
        lines=piece.splitlines(keepends=True)
        starts=sorted({0,len(lines),*[t.map[0] for t in MarkdownIt().parse(piece) if t.map and t.level==0]})
        batch=''
        for left,right in zip(starts,starts[1:]):
            block=''.join(lines[left:right])
            if batch and len(batch)+len(block)>12000:
                result.append(batch);batch=''
            batch+=block
        if batch: result.append(batch)
    return result


def localize_note(markdown,source,call,checkpoint=None,budget=120,report=None):
    """Optional correction; unavailable/invalid output retains every input byte."""
    import json
    pieces=[]
    for piece in _language_pieces(markdown):
        # A foreign-language heading does not require retranslating the entire
        # otherwise-correct chapter. Preserve its surrounding prose byte-for-byte.
        heading, separator, rest = piece.partition('\n')
        if separator and re.match(r'^#{2,6} ', heading) and language_mismatch(source, heading) and not language_mismatch(source, rest):
            pieces.extend((heading + separator, rest))
        else:
            pieces.append(piece)
    allowance=min(360,max(120,len(pieces)*10)) if budget is None else budget
    deadline=time.monotonic()+allowance
    result=[];unavailable=False;consecutive_failures=0
    report=report if report is not None else {}
    for piece in pieces:
        if not language_mismatch(source,piece):
            result.append(piece);continue
        if unavailable or len(piece)>14000 or time.monotonic()>=deadline:
            reasons=report.setdefault('unresolved',{})
            reason='provider_unavailable' if unavailable else 'oversized_section' if len(piece)>14000 else 'budget_exhausted'
            reasons[reason]=reasons.get(reason,0)+1
            result.append(piece);continue
        protected={};draft=piece
        for index,(left,right) in reversed(list(enumerate(_protected(piece)))):
            key=f'XYZ_VERBATIM_{index}_KEEP'
            protected[key]=piece[left:right];draft=draft[:left]+key+draft[right:]
        system=source_language_lock(source)+'\nCorrect ONLY the language of this Markdown. Preserve every detail, argument, qualification and chapter heading meaning; do not summarize, reorganize or add advice. Keep heading levels/numbers, all numbers, timestamps, URLs, media markers and XYZ_VERBATIM placeholders exactly. Return JSON {"text":"complete corrected Markdown"}.'
        try:
            if checkpoint: checkpoint()
            report['attempted']=report.get('attempted',0)+1
            try:
                value=call(system,json.dumps({'markdown':draft},ensure_ascii=False),min(45,max(1,deadline-time.monotonic())))
            except Exception as error:
                consecutive_failures += 1
                status=getattr(error,'status_code',None)
                unavailable=status in (401,403,404) or consecutive_failures>=3
                if isinstance(status,int) and 100<=status<=599: report['provider_http_status']=status
                report['provider_error_type']=type(error).__name__
                raise
            consecutive_failures=0
            if checkpoint: checkpoint()
            candidate=value.get('text') if isinstance(value,dict) else None
            if not isinstance(candidate,str) or not candidate.strip(): raise ValueError('Missing corrected text')
            for key,original in protected.items():
                if candidate.count(key)!=1: raise ValueError('Changed source block')
                candidate=candidate.replace(key,original)
            before=_invariants(piece);after=_invariants(candidate)
            changed=[name for name,left,right in zip(('media_urls','numeric_values','heading_levels'),before,after) if left!=right]
            if media_times(candidate)!=media_times(piece): changed.append('media_order')
            if language_mismatch(source,candidate): changed.append('language')
            if changed:
                rejected=report.setdefault('rejected_checks',{})
                for name in changed: rejected[name]=rejected.get(name,0)+1
                raise ValueError('Language correction changed source anchors')
            # Keep original block separators, including the boundary before a
            # following heading, independent of the model's whitespace choice.
            tail=piece[len(piece.rstrip('\r\n')):]
            result.append(candidate.rstrip('\r\n')+tail)
            report['corrected']=report.get('corrected',0)+1
        except Exception as error:
            if is_cancellation(error): raise
            report['retained']=report.get('retained',0)+1
            result.append(piece)
    return ''.join(result)
