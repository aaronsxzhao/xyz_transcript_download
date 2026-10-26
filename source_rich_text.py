"""Source inline formatting, without executing HTML or rewriting original prose."""
import re
import unicodedata


def escape_text(value):
    return re.sub(r'([\\`*{}_~\[\]<>])', r'\\\1', str(value or ''))


def inline_code(value):
    value = str(value)
    fence = '`' * max(1, max((len(match[0]) + 1 for match in re.finditer(r'`+', value)), default=1))
    pad = ' ' if not value.isspace() and (value.startswith(('`', ' ')) or value.endswith(('`', ' '))) else ''
    return fence + pad + value + pad + fence


def emphasis(value, marker):
    """Keep whitespace outside delimiters so CommonMark recognizes the mark."""
    match = re.fullmatch(r'(\s*)([\s\S]*?)(\s*)', value)
    before, text, after = match.groups()
    if not text:
        return value
    # Punctuation next to CJK prose cannot close emphasis reliably. Preserve
    # the punctuation verbatim outside the delimiter rather than print stars.
    leading = trailing = ''
    while text and unicodedata.category(text[0]).startswith('P') and text[0] not in '\\*`[':
        leading += text[0]; text = text[1:]
    while text and unicodedata.category(text[-1]).startswith('P') and text[-1] not in '\\*`]':
        trailing = text[-1] + trailing; text = text[:-1]
    return before + leading + (marker + text + marker if text else '') + trailing + after


def draft_inline(raw, styles=(), links=(), start=0, end=None):
    """Interpret Draft.js UTF-16 offsets; keep crossing ranges well nested.

    Invalid ranges never consume source text. Callers can render a slice around
    an atomic media entity while retaining the surrounding text's formatting.
    """
    offsets = {0:0}
    units = 0
    for index, char in enumerate(raw):
        units += 2 if ord(char) > 0xffff else 1
        offsets[units] = index + 1
    end = units if end is None else end
    if start not in offsets or end not in offsets:
        return ''
    low, high = offsets[start], offsets[end]
    ranges = []
    for row in styles:
        kind = str(row.get('style', '')).upper()
        marker = {'BOLD':'**', 'ITALIC':'*', 'STRIKETHROUGH':'~~', 'CODE':'`'}.get(kind)
        left, length = row.get('offset'), row.get('length')
        if marker is None or not isinstance(left,int) or isinstance(left,bool) or not isinstance(length,int) or isinstance(length,bool) or length <= 0:
            continue
        if left not in offsets or left+length not in offsets:
            continue
        a,b = max(low,offsets[left]),min(high,offsets[left+length])
        if kind!='CODE':
            while a<b and raw[a].isspace(): a+=1
            while b>a and raw[b-1].isspace(): b-=1
        # Keep punctuation at the boundary outside emphasis when surrounded by
        # prose; the original characters and their order remain unchanged.
        if kind!='CODE':
            while a<b and unicodedata.category(raw[a]).startswith('P') and a>0 and raw[a-1].isalnum(): a+=1
            while b>a and unicodedata.category(raw[b-1]).startswith('P') and b<len(raw) and raw[b].isalnum(): b-=1
        if a<b: ranges.append((a,b,kind,marker))
    for row in links:
        left,length=row.get('offset'),row.get('length')
        if isinstance(left,int) and isinstance(length,int) and length>0 and left in offsets and left+length in offsets:
            a,b=max(low,offsets[left]),min(high,offsets[left+length])
            if a<b and row.get('url'): ranges.append((a,b,'LINK',row['url']))
    boundaries=sorted({low,high,*[point for a,b,_,_ in ranges for point in (a,b)]})
    stack=[];output=[]
    for left,right in zip(boundaries,boundaries[1:]):
        active={kind:mark for a,b,kind,mark in ranges if a<=left and b>=right}
        # Keep existing nesting when possible; reopen crossing ranges using
        # the other emphasis delimiter, avoiding ambiguous runs of stars.
        wanted=[(kind,mark) for kind,mark in stack if kind in active]
        wanted += [(kind,active[kind]) for kind in ('LINK','BOLD','ITALIC','STRIKETHROUGH','CODE') if kind in active and all(k!=kind for k,_ in wanted)]
        common=0
        while common<min(len(stack),len(wanted)) and stack[common][0]==wanted[common][0]: common+=1
        for kind,mark in reversed(stack[common:]): output.append(']('+mark+')' if kind=='LINK' else mark)
        stack=stack[:common]
        for kind,mark in wanted[common:]:
            tail=output[-1][-1:] if output else ''
            if kind=='BOLD': mark='__' if tail=='*' else '**'
            elif kind=='ITALIC': mark='_' if tail=='*' else '*'
            elif kind=='CODE':
                position=next(b for a,b,k,_ in ranges if k=='CODE' and a<=left<b)
                mark='`'*max(1,max((len(m[0])+1 for m in re.finditer(r'`+',raw[left:position])),default=1))
            if kind=='CODE':
                code_end=max(b for a,b,k,_ in ranges if k=='CODE' and a<=left<b)
                code=raw[left:code_end]
                pad=' ' if not code.isspace() and (code.startswith(('`',' ')) or code.endswith(('`',' '))) else ''
                output.append(mark+pad)
                mark=pad+mark
            else:
                output.append('[' if kind=='LINK' else mark)
            stack.append((kind,mark))
        text=raw[left:right]
        output.append(text if 'CODE' in active else escape_text(text).replace('\n','  \n'))
    for kind,mark in reversed(stack): output.append(']('+mark+')' if kind=='LINK' else mark)
    return ''.join(output)
