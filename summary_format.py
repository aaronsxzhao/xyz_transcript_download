"""Tolerate model packaging differences without inventing reading content."""
import json
import re

from summary_errors import SummaryOutputError


def _without_trailing_commas(value: str) -> str:
    output = []
    quoted = escaped = False
    for index, char in enumerate(value):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ',':
            following = index + 1
            while following < len(value) and value[following].isspace():
                following += 1
            if following < len(value) and value[following] in '}]':
                continue
        output.append(char)
    return ''.join(output)


def extract_model_json(content: str):
    """Decode fenced/prefixed JSON, including trailing commas, string-aware."""
    decoder = json.JSONDecoder()
    opening = re.compile(r'[\[{]')
    candidates = [content.strip()]
    candidates.extend(match.group(1) for match in re.finditer(r'```(?:json)?\s*([\s\S]*?)```', content, re.I))
    for candidate in candidates:
        for repair in (False, True):
            text = _without_trailing_commas(candidate) if repair else candidate
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            offset = 0
            while match := opening.search(text, offset):
                start = match.start()
                try:
                    value, _ = decoder.raw_decode(text, start)
                    if isinstance(value, (dict, list)):
                        return value
                except json.JSONDecodeError:
                    # Skip only a complete bracketed preamble. Never salvage
                    # one nested point from a truncated outer JSON document.
                    depth, quoted, escaped = 0, False, False
                    for index in range(start, len(text)):
                        char = text[index]
                        if quoted:
                            if escaped:
                                escaped = False
                            elif char == '\\':
                                escaped = True
                            elif char == '"':
                                quoted = False
                        elif char == '"':
                            quoted = True
                        elif char in '[{':
                            depth += 1
                        elif char in ']}':
                            depth -= 1
                            if depth == 0:
                                offset = index + 1
                                break
                    else:
                        break
    raise json.JSONDecodeError('No valid JSON found in response', content, 0)


def normalize_summary_fields(data):
    from reading_language import chinese_source
    if isinstance(data, list):
        data = {'key_points': data}
    elif isinstance(data, str):
        data = {'overview': data}
    if not isinstance(data, dict):
        raise SummaryOutputError('invalid')
    for key in ('data', 'result', 'summary'):
        if not any(name in data for name in ('overview', 'key_points', 'content', 'body')) and isinstance(data.get(key), dict):
            data = data[key]

    def text(value):
        if isinstance(value, str):
            return value if value.strip() else ''
        if isinstance(value, list):
            return '\n\n'.join(part for item in value if (part := text(item)))
        if isinstance(value, dict):
            return text(next((value[key] for key in ('summary', 'text', 'content', 'body') if value.get(key)), ''))
        return ''

    overview = text(data.get('overview')) or text(data.get('summary')) or text(data.get('content')) or text(data.get('body'))
    topics = data.get('topics') or []
    topics = [topics] if isinstance(topics, str) else topics
    topics = [item.strip() for item in topics if isinstance(item, str) and item.strip()] if isinstance(topics, list) else []
    takeaways = data.get('takeaways') or []
    takeaways = [takeaways] if isinstance(takeaways, str) else takeaways
    takeaways = [part for item in takeaways if (part := text(item))] if isinstance(takeaways, list) else []
    rows = data.get('key_points') or []
    if isinstance(rows, dict):
        if any(key in rows for key in ('topic', 'summary', 'text', 'content', 'body')):
            rows = [rows]
        else:
            rows = [{'topic': key, 'summary': text(value)} for key, value in rows.items()]
    if isinstance(rows, str):
        rows = [rows]
    points = []
    for row in rows if isinstance(rows, list) else []:
        body = text(row)
        if not body:
            continue
        point = row if isinstance(row, dict) else {}
        fallback_topic = '其他内容' if chinese_source(overview or body) else 'Other content'
        points.append({'topic': text(point.get('topic')) or fallback_topic, 'summary': body,
                       'original_quote': text(point.get('original_quote')), 'timestamp': text(point.get('timestamp'))})
    if not overview and not points:
        raise SummaryOutputError('invalid')
    return {'overview': overview, 'topics': topics, 'takeaways': takeaways, 'key_points': points}
