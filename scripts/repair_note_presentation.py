"""Backed-up repair of the two explicitly reported language/order defects.

    Use saved notes/transcripts and the owner's saved provider. Never download
    media, retranscribe, change preferences or emit source/provider secrets.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
TARGETS=('db675cfd-a5c','27c3cdaa-882')
VERSION='note-language-order-v1'
PROGRESS={}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def original_suffix(markdown):
    from markdown_it import MarkdownIt
    lines=markdown.splitlines(keepends=True)
    for token in MarkdownIt().parse(markdown):
        if token.type=='heading_open' and token.tag=='h2' and token.level==0 and lines[token.map[0]].strip()=='## Original post / article':
            return ''.join(lines[:token.map[0]]),''.join(lines[token.map[0]:])
    return markdown,''


def repair():
    from api.supabase_client import get_supabase_admin_client
    from api.user_settings import get_user_settings
    from api.llm_settings import resolve_llm_settings
    from note_summarizer import NoteSummarizer
    from note_presentation import media_times,language_mismatch
    from reading_editor import _media,_verbatim_blocks
    from video_task_db import get_video_task_db
    from scripts.repair_source_coverage import verified_upload
    client=get_supabase_admin_client();db=get_video_task_db()
    owners=client.table('video_tasks').select('user_id').eq('id','bc2c988b-2b4').limit(1).execute().data or []
    if len(owners)!=1: raise RuntimeError('Requested owner unavailable')
    owner=owners[0]['user_id']
    bucket=client.storage.get_bucket('application-backups')
    if (bucket.get('public') if isinstance(bucket,dict) else getattr(bucket,'public',False)):
        raise RuntimeError('Repair backups must be private')
    storage=client.storage.from_('application-backups')
    report={'note_presentation_repair':True,'repaired':0,'already_repaired':0,'source_unchanged':0,'backward_anchors':0,'language_mismatches':0}
    for ident in TARGETS:
        task=db.get_task(ident,owner)
        if not task or task['status']!='success': raise RuntimeError('Reported task is not ready for repair')
        transcript=task.get('transcript') or {}
        source=transcript.get('text') or ''
        if not source.strip() or not task.get('markdown'): raise RuntimeError('Saved source unavailable')
        prefix=f'note-presentation-repairs/{owner}/{ident}/{VERSION}'
        files=storage.list(prefix,{'search':'complete.json','limit':10})
        if any(item.get('name')=='complete.json' for item in files):
            report['already_repaired']+=1;continue
        original=task['markdown'];source_hash=digest(transcript)
        attempt=os.environ.get('GITHUB_RUN_ID','manual')+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1')
        verified_upload(storage,prefix+'/'+attempt+'-before.json',{'task':task,'source_hash':source_hash})
        preferences=get_user_settings(owner)
        settings=resolve_llm_settings(preferences)
        engine=NoteSummarizer(**settings)
        body,suffix=original_suffix(original)
        needed_language=language_mismatch(source,body)
        language_report={}
        PROGRESS.update(case='books' if ident==TARGETS[0] else 'twitter',phase='presentation',language=language_report)
        try:
            candidate=engine._finish_presentation(body,task['title'],'toc' in task.get('formats',[]),source,language_budget=900,language_report=language_report)
            # Retain accepted units across bounded retries of only the units
            # that failed language correction. Never restart completed work or
            # retry an unavailable provider.
            for retry in range(2):
                if not language_mismatch(source,candidate) or language_report.get('provider_error_type'):
                    break
                verified_upload(storage,prefix+'/'+attempt+f'-partial-{retry}.json',{'markdown':candidate,'source_hash':source_hash,'checks':language_report})
                candidate=engine._finish_presentation(candidate,task['title'],'toc' in task.get('formats',[]),source,language_budget=120,language_report=language_report)
        finally:
            engine.client.close()
        if language_mismatch(source,candidate): raise RuntimeError('Language correction did not finish; original retained')
        times=media_times(candidate)
        if any(right<left for left,right in zip(times,times[1:])):
            raise RuntimeError('Chronology correction did not finish; original retained')
        if Counter(times)!=Counter(media_times(body)) or not _media(body).issubset(_media(candidate)):
            raise RuntimeError('Repair changed source media; original retained')
        if any(block not in candidate for block in _verbatim_blocks(body)):
            raise RuntimeError('Repair changed a source quotation or code block')
        if suffix: candidate=candidate.rstrip('\r\n')+'\n\n'+suffix
        verified_upload(storage,prefix+'/'+attempt+'-candidate.json',{'markdown':candidate,'source_hash':source_hash})
        current=client.table('video_tasks').select('markdown,transcript_json,status').eq('id',ident).eq('user_id',owner).single().execute().data
        current_source=current.get('transcript_json') or '{}'
        if isinstance(current_source,str): current_source=json.loads(current_source)
        if current['markdown']!=original or digest(current_source)!=source_hash or current['status']!='success':
            raise RuntimeError('Source or note changed during repair')
        if not any(row.get('content')==original for row in db.get_versions(ident)):
            db.add_version(ident,original,task.get('style',''),task.get('model',''))
        db.complete_task(ident,candidate,task.get('style') or 'detailed',engine.model if needed_language else task.get('model',''),owner,task.get('error') or '')
        saved=client.table('video_tasks').select('markdown,transcript_json').eq('id',ident).eq('user_id',owner).single().execute().data
        stored_source=saved.get('transcript_json') or '{}'
        if isinstance(stored_source,str): stored_source=json.loads(stored_source)
        if saved['markdown']!=candidate or digest(stored_source)!=source_hash:
            raise RuntimeError('Repair readback failed; private backup retained')
        verified_upload(storage,prefix+'/complete.json',{'source_hash':source_hash,'note_hash':digest(candidate),'before':prefix+'/'+attempt+'-before.json','revision':os.environ.get('GITHUB_SHA','manual')})
        report['repaired']+=1;report['source_unchanged']+=1
    return report


if __name__=='__main__':
    from scripts.repair_source_coverage import main
    try: print(json.dumps(main(repair)))
    except Exception as error:
        print(json.dumps({'note_presentation_repair':False,'error_type':type(error).__name__,**PROGRESS}))
        raise SystemExit(1)
