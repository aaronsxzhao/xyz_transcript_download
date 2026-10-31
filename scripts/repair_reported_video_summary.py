"""Retry only the uniquely identified Stanford lecture reported on 31 October.

Use the existing owner API; emit fixed statuses, never source or credentials.
"""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import repair_reported_summary as bootstrap
from scripts.repair_reported_transcript import request_json


def repair(settings):
    from api.supabase_client import get_supabase_admin_client
    from jose import jwt
    rows = (get_supabase_admin_client().table('video_tasks')
            .select('id,user_id,title,status,created_at')
            .eq('platform', 'bilibili').ilike('title', '%斯坦福大学%如何创业%')
            .gte('created_at', '2026-10-31T00:00:00').execute().data)
    rows = [row for row in rows if '第1讲' in row['title'] and '如何开始创业' in row['title']]
    if len(rows) != 1 or not rows[0].get('user_id'):
        raise RuntimeError('Reported task is not uniquely identifiable')
    row = rows[0]
    now = int(time.time())
    token = jwt.encode({'sub': row['user_id'], 'aud': 'authenticated', 'role': 'authenticated',
                        'iat': now, 'exp': now + 2400}, settings['SUPABASE_JWT_SECRET'], algorithm='HS256')
    path = '/api/video-notes/tasks/' + row['id']
    expected = os.environ.get('EXPECTED_REVISION')
    if not expected or request_json('/api/health', token).get('revision') != expected:
        raise RuntimeError('Expected release is not live')
    task = request_json(path, token)
    before = task.get('transcript')
    if task['status'] in ('failed', 'cancelled'):
        request_json(path + '/retry', token, {})
    elif task['status'] != 'success' and task['status'] not in (
            'pending', 'downloading', 'parsing', 'transcribing', 'summarizing', 'saving'):
        raise RuntimeError('Task cannot be safely retried')
    previous = None
    for _ in range(360):
        task = request_json(path, token)
        status = task['status']
        if status != previous:
            print(json.dumps({'repair': 'reported_video_summary', 'status': status}), flush=True)
            previous = status
        if status == 'success':
            if not (task.get('markdown') or '').strip() or not task.get('versions'):
                raise RuntimeError('Saved note is missing')
            if before and task.get('transcript') != before:
                raise RuntimeError('Saved transcript changed')
            return {'repair': 'reported_video_summary', 'status': 'verified',
                    'saved_versions': len(task['versions']), 'transcript_preserved': bool(before)}
        if status in ('failed', 'cancelled'):
            raise RuntimeError('Reported video recovery did not complete')
        time.sleep(5)
    raise TimeoutError('Reported video is still processing')


if __name__ == '__main__':
    bootstrap.repair = repair
    try:
        print(json.dumps(bootstrap.main()))
    except Exception as error:
        print(json.dumps({'repair': 'reported_video_summary', 'status': 'failed',
                          'error_type': type(error).__name__}))
        sys.exit(1)
