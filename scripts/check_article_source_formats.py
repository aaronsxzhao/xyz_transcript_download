"""Read public originals and report formatting counts; no account or model calls."""
import json
import re
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from markdown_it import MarkdownIt
from social_content import _json,_twitter_article_body,html_markdown


def inline_styles(markdown):
    return sum(token.type=='strong_open' for block in MarkdownIt().parse(markdown) for token in block.children or [])


def check():
    for ident in ('2114386050638336082','2010751592346030461'):
        data=_json('https://api.fxtwitter.com/2/status/'+ident,time.monotonic()+25)
        article=(data.get('status') or data.get('tweet') or {}).get('article') or {}
        blocks=(article.get('content') or article.get('content_state') or {}).get('blocks') or []
        marks=[mark for block in blocks for mark in block.get('inlineStyleRanges',[])]
        body,_=_twitter_article_body(article,'https://x.com/i/status/'+ident)
        print(json.dumps({'source':'twitter','id':ident,'blocks':len(blocks),'bold_ranges':sum(str(mark.get('style','')).upper()=='BOLD' for mark in marks),'italic_ranges':sum(str(mark.get('style','')).upper()=='ITALIC' for mark in marks),'rendered_bold':inline_styles(body),'characters':len(body)}),flush=True)
    from social_content import SocialSourceError
    try:
        post=_json('https://timdenning.substack.com/api/v1/posts/once-you-understand-neuroplasticity',time.monotonic()+25)
        raw=post.get('body_html') or ''
        body=html_markdown(raw,'https://timdenning.substack.com/p/once-you-understand-neuroplasticity')
        print(json.dumps({'source':'substack','semantic_bold_tags':len(re.findall(r'<(?:strong|b)(?:\s|>)',raw,re.I)),'rendered_bold':inline_styles(body),'characters':len(body)}),flush=True)
    except SocialSourceError as error:
        print(json.dumps({'source':'substack','access_unavailable':True,'reason':str(error)}),flush=True)


if __name__=='__main__':
    try:check()
    except Exception as error:
        print(json.dumps({'source_format_probe_failed':True,'error_type':type(error).__name__}),flush=True)
        raise SystemExit(1)
