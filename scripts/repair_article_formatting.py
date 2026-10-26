"""Restore available original article formatting without changing source prose.

Only the requested owner's successful original-text articles are eligible.
Unavailable/changed sources remain untouched. Each repair adds a saved version;
existing note versions remain available for undo. No summary/model calls.
"""
import json
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from markdown_it import MarkdownIt


def visible_text(markdown):
    parts=[]
    def visit(tokens):
        for token in tokens:
            if token.type=='image': continue
            if token.children: visit(token.children)
            elif token.type in ('text','code_inline','code_block','fence'):parts.append(token.content)
            elif token.type in ('softbreak','hardbreak'):parts.append(' ')
    visit(MarkdownIt().parse(markdown))
    return re.sub(r'\s+','', ''.join(parts))


def richness(markdown):
    return sum(token.type in ('strong_open','em_open','s_open','code_inline','link_open')
        for block in MarkdownIt('commonmark').enable('strikethrough').parse(markdown)
        for token in block.children or [])


def source_anchors(markdown):
    from collections import Counter
    codes=Counter();destinations=Counter()
    def visit(tokens):
        for token in tokens:
            if token.type in ('code_inline','code_block','fence'):
                codes[(token.type,token.content)]+=1
            if token.type in ('link_open','image'):
                destinations[(token.type,token.attrGet('href') if token.type=='link_open' else token.attrGet('src'))]+=1
            if token.children: visit(token.children)
    visit(MarkdownIt().parse(markdown))
    return codes,destinations


def repair_one(db,task,resolve):
    if task.get('style')!='original' or task.get('status')!='success':return 'ineligible'
    from social_content import SocialSourceError
    try: source=resolve(task['url'])
    except SocialSourceError:return 'source_unavailable'
    if source.media:return 'ineligible'
    candidate=source.markdown()
    previous=task.get('markdown') or ''
    if candidate==previous or richness(candidate)<=richness(previous):return 'unchanged'
    if visible_text(candidate)!=visible_text(previous):return 'changed_source_kept'
    if any(old-new for old,new in zip(source_anchors(previous),source_anchors(candidate))):return 'changed_source_kept'
    current=db.get_task(task['id'],task['user_id'])
    if not current or current.get('status')!='success' or current.get('markdown')!=previous:return 'concurrent_change_kept'
    db.complete_task(task['id'],candidate,'original','',task['user_id'])
    saved=db.get_task(task['id'],task['user_id'])
    if not saved or saved.get('markdown')!=candidate:raise RuntimeError('Article format save was not confirmed')
    return 'repaired'


def repair():
    from api.supabase_client import get_supabase_admin_client
    from video_task_db import get_video_task_db
    from content_sources import resolve_content
    client=get_supabase_admin_client()
    owners=client.table('video_tasks').select('user_id').eq('id','bc2c988b-2b4').limit(1).execute().data or []
    if len(owners)!=1:raise RuntimeError('Requested article owner unavailable')
    owner=owners[0]['user_id'];db=get_video_task_db()
    rows=client.table('video_tasks').select('id').eq('user_id',owner).eq('style','original').eq('status','success').in_('platform',['twitter','substack','web']).order('updated_at',desc=True).limit(20).execute().data or []
    report={'article_format_repair':True,'checked':0,'repaired':0,'summary_writes':False}
    for row in rows:
        task=db.get_task(row['id'],owner)
        if not task:continue
        report['checked']+=1
        outcome=repair_one(db,task,resolve_content)
        report[outcome]=report.get(outcome,0)+1
    return report


if __name__=='__main__':
    from scripts.repair_source_coverage import main
    try:print(json.dumps(main(repair)))
    except Exception as error:
        print(json.dumps({'article_format_repair':False,'error_type':type(error).__name__}))
        raise SystemExit(1)
