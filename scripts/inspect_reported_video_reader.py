"""Read-only diagnostics for the reported blank reader; never log source text."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import repair_reported_summary as bootstrap


def inspect(settings):
    from api.supabase_client import get_supabase_admin_client
    client = get_supabase_admin_client()
    rows = (client.table('video_tasks').select('id,status,markdown,transcript_json,user_id,updated_at')
            .ilike('title', '%谷爱凌%观察性自我%').eq('platform', 'bilibili').limit(5).execute().data or [])
    report = []
    for row in rows:
        from jose import jwt
        from scripts.repair_reported_transcript import request_json
        now = int(time.time())
        token = jwt.encode({'sub':row['user_id'],'aud':'authenticated','role':'authenticated',
                            'iat':now,'exp':now+300},settings['SUPABASE_JWT_SECRET'],algorithm='HS256')
        note = request_json('/api/video-notes/tasks/'+row['id']+'?view=note', token)
        versions = (client.table('video_task_versions').select('content,created_at').eq('task_id', row['id'])
                    .order('created_at', desc=True).limit(5).execute().data or [])
        report.append({'status': row['status'], 'markdown_chars': len(row.get('markdown') or ''),
                       'api_markdown_chars':len(note.get('markdown') or ''),
                       'api_status':note.get('status'),
                       'has_transcript': bool(row.get('transcript_json')),
                       'version_chars': [len(version.get('content') or '') for version in versions]})
    return {'reader_diagnostics': report}


if __name__ == '__main__':
    bootstrap.repair = inspect
    try:
        print(json.dumps(bootstrap.main()))
    except Exception as error:
        print(json.dumps({'reader_diagnostics': 'failed', 'error_type': type(error).__name__}))
        sys.exit(1)
