"""Read compatibility for the old HTML adapter's broken linked-image blocks."""
import re
from urllib.parse import urlsplit


def repair_web_attribution(markdown, url):
    """Correct the generated metadata wrapper, never an article's own prose."""
    host = urlsplit(url).hostname or ''
    if not host: return markdown
    from social_content import _escape
    pattern = r'\A(#[^\n]+\n\n)Author: ' + re.escape(_escape(host)) + r'(\n\n\[Original source\]\()'
    return re.sub(pattern, lambda match:match[1] + 'Source: ' + _escape(host) + match[2], markdown, count=1)

_BROKEN_IMAGE = re.compile(
    r'^ {0,3}\[[ \t]*\r?\n(?:[ \t]*\r?\n)+'
    r'[ \t]*(!\[[^\r\n]*\]\([^\r\n]+\))[ \t]*\r?\n(?:[ \t]*\r?\n)+'
    r'[ \t]*\]\((https?://[^\s()]+)\)([^\r\n]*)$', re.MULTILINE)


def repair_article_markdown(markdown: str) -> str:
    """Repair only a standalone link/image split produced by the old adapter.

    Source text and stored versions stay unchanged. Fenced/indented code and
    HTML examples are excluded using the same CommonMark block boundaries.
    """
    matches = list(_BROKEN_IMAGE.finditer(markdown))
    if not matches:
        return markdown
    from markdown_it import MarkdownIt
    parser = MarkdownIt()
    lines = markdown.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    protected = [(offsets[t.map[0]], offsets[t.map[1]]) for t in parser.parse(markdown)
                 if t.map and t.type in ('fence', 'code_block', 'html_block')]
    for match in reversed(matches):
        if any(start < match.end() and end > match.start() for start, end in protected):
            continue
        image, target, caption = match.groups()
        linked = f'[{image}]({target})'
        tokens = parser.parse(linked)
        children = tokens[1].children if len(tokens) == 3 and tokens[1].type == 'inline' else []
        if [t.type for t in children or []] != ['link_open', 'image', 'link_close']:
            continue
        repaired = linked + ('\n\n' + caption if caption else '')
        markdown = markdown[:match.start()] + repaired + markdown[match.end():]
    return markdown


def readable_article_task(task):
    if task and task.get('style') == 'original' and task.get('platform') in ('twitter', 'substack', 'web'):
        markdown = repair_article_markdown(task.get('markdown') or '')
        if task.get('platform') == 'web': markdown = repair_web_attribution(markdown, task.get('url') or '')
        return {**task, 'markdown': markdown}
    return task
