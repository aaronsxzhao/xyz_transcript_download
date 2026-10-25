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
        for unit in units:
            times=media_times(unit)
            if times: groups.append([times[0],parent,unit])
            elif groups and groups[-1][1]==parent: groups[-1][2]+=unit
            elif groups: groups.append([groups[-1][0],parent,unit])
            else: prefix+=parent+separator+unit
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
    if not re.search(r'[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]',source):
        return han>=1
    words=len(re.findall(r'\b[A-Za-z]{2,}\b',text))
    return chinese_source(source) and words>=40 and han<words/8


def _invariants(text):
    urls=Counter(re.findall(r'https?://[^\s<>"\)]+|/data/(?:screenshots|thumbnails)/[^\s\)]+|(?:Screenshot-|\*?Content-)\[\d+(?::\d+){1,2}\]',text))
    numbers=Counter(re.findall(r'(?<!\w)\d+(?:[.,:]\d+)*(?:%|\b)',text))
    headings=[t.tag for t in MarkdownIt().parse(text) if t.type=='heading_open']
    return urls,numbers,headings


def localize_note(markdown,source,call,checkpoint=None,budget=120,report=None):
    """Optional correction; unavailable/invalid output retains every input byte."""
    import json
    deadline=time.monotonic()+budget
    prefix,sections=_sections(markdown,(2,3))
    pieces=[prefix,*sections];result=[];unavailable=False
    report=report if report is not None else {}
    for piece in pieces:
        if unavailable or not language_mismatch(source,piece) or len(piece)>14000 or time.monotonic()>=deadline:
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
                unavailable=True
                status=getattr(error,'status_code',None)
                if isinstance(status,int) and 100<=status<=599: report['provider_http_status']=status
                report['provider_error_type']=type(error).__name__
                raise
            if checkpoint: checkpoint()
            candidate=value.get('text') if isinstance(value,dict) else None
            if not isinstance(candidate,str) or not candidate.strip(): raise ValueError('Missing corrected text')
            for key,original in protected.items():
                if candidate.count(key)!=1: raise ValueError('Changed source block')
                candidate=candidate.replace(key,original)
            if _invariants(candidate)!=_invariants(piece) or media_times(candidate)!=media_times(piece) or language_mismatch(source,candidate):
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
